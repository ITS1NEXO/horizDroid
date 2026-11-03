//! The Dressing Room's saved skins and capes, and which of them the player wears.
//!
//! Plain files under one folder, no JSON and no dependencies, so the rules here (dedupe, limits,
//! atomic writes, a selection that can never point at a missing file) are unit-tested on any host:
//!
//! ```text
//! <root>/skins/<id>.png    validated 64x64 or 64x32 skins
//! <root>/capes/<id>.png    validated 64x32 or 22x17 capes
//! <root>/selection.txt     `skin=<id>`, `cape=<id>`, `model=classic|slim`
//! ```
//!
//! The caller validates the picture (`launcher/src/skins.rs`) before [`Store::add`]; the store
//! only keeps the bytes it is given. Ids come from the bytes themselves, so importing the same
//! picture twice keeps one file. The selection is the player's, not an offline name's: Android
//! plays one offline name, and a chosen skin should show whatever that name is.
use std::{
    fs, io,
    path::{Path, PathBuf},
    time::SystemTime,
};

pub const MAX_SKINS: usize = 32;
pub const MAX_CAPES: usize = 16;
/// The largest picture the store keeps (`launcher/src/skins.rs` `MAX_IMPORT_BYTES`).
pub const MAX_BYTES: usize = 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Skin,
    Cape,
}

impl Kind {
    fn folder(self) -> &'static str {
        match self {
            Kind::Skin => "skins",
            Kind::Cape => "capes",
        }
    }
    fn limit(self) -> usize {
        match self {
            Kind::Skin => MAX_SKINS,
            Kind::Cape => MAX_CAPES,
        }
    }
    fn word(self) -> &'static str {
        match self {
            Kind::Skin => "skin",
            Kind::Cape => "cape",
        }
    }
}

/// Classic (four-pixel arms, "Steve") or slim (three-pixel arms, "Alex").
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Model {
    #[default]
    Classic,
    Slim,
}

/// What the player wears: a skin and a cape by id, and the model the skin is drawn on.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Selection {
    pub skin: Option<String>,
    pub cape: Option<String>,
    pub model: Model,
}

/// The files the game should draw, only ever ones that exist.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Worn {
    pub skin: Option<PathBuf>,
    pub cape: Option<PathBuf>,
    pub slim: bool,
}

pub struct Store {
    root: PathBuf,
}

/// FNV-1a over the bytes, with the length: a stable name for a picture. Not a security hash; a
/// clash is caught by comparing bytes in [`Store::add`].
fn id_of(bytes: &[u8]) -> String {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for &b in bytes {
        hash ^= u64::from(b);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{hash:016x}-{:x}", bytes.len())
}

/// Ids are file names: hex digits and one dash, so nothing read from `selection.txt` can leave the folder.
fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 40
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b) || b == b'-')
}

fn write_atomically(to: &Path, bytes: &[u8]) -> io::Result<()> {
    let part = to.with_extension("part");
    let result = fs::write(&part, bytes).and_then(|()| fs::rename(&part, to));
    if result.is_err() {
        let _ = fs::remove_file(&part);
    }
    result
}

impl Store {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Store { root: root.into() }
    }

    fn folder(&self, kind: Kind) -> PathBuf {
        self.root.join(kind.folder())
    }

    /// The file of a saved picture, if `id` is a well-formed id.
    pub fn path(&self, kind: Kind, id: &str) -> Option<PathBuf> {
        valid_id(id).then(|| self.folder(kind).join(format!("{id}.png")))
    }

    /// Saved ids, newest first.
    pub fn list(&self, kind: Kind) -> Vec<String> {
        let mut found: Vec<(Option<SystemTime>, String)> = fs::read_dir(self.folder(kind))
            .into_iter()
            .flatten()
            .flatten()
            .filter_map(|entry| {
                let name = entry.file_name().into_string().ok()?;
                let id = name.strip_suffix(".png")?;
                if !valid_id(id) || !entry.file_type().ok()?.is_file() {
                    return None;
                }
                Some((entry.metadata().ok()?.modified().ok(), id.to_string()))
            })
            .collect();
        found.sort_by(|a, b| b.cmp(a));
        found.into_iter().map(|(_, id)| id).collect()
    }

    pub fn read(&self, kind: Kind, id: &str) -> Option<Vec<u8>> {
        use io::Read;
        let mut bytes = Vec::new();
        fs::File::open(self.path(kind, id)?)
            .ok()?
            .take(MAX_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .ok()?;
        (bytes.len() <= MAX_BYTES).then_some(bytes)
    }

    /// Keeps a validated picture and returns its id. The same picture is kept once.
    pub fn add(&self, kind: Kind, bytes: &[u8]) -> Result<String, String> {
        if bytes.is_empty() || bytes.len() > MAX_BYTES {
            return Err("The PNG must be at most 1 MiB.".into());
        }
        let id = id_of(bytes);
        let folder = self.folder(kind);
        let to = folder.join(format!("{id}.png"));
        if let Some(have) = self.read(kind, &id) {
            return if have == bytes {
                Ok(id)
            } else {
                Err("Another saved picture has the same name; try a different file.".into())
            };
        }
        if self.list(kind).len() >= kind.limit() {
            return Err(format!(
                "You can keep {} {}s; remove one first.",
                kind.limit(),
                kind.word()
            ));
        }
        fs::create_dir_all(&folder).map_err(|e| format!("{}: {e}", folder.display()))?;
        write_atomically(&to, bytes).map_err(|e| format!("{}: {e}", to.display()))?;
        Ok(id)
    }

    /// What was last chosen. A skin or cape whose file is gone is dropped, so the game falls
    /// back to the default skin instead of failing.
    pub fn selection(&self) -> Selection {
        let text = fs::read_to_string(self.root.join("selection.txt")).unwrap_or_default();
        let mut chosen = Selection::default();
        for line in text.lines() {
            let Some((key, value)) = line.split_once('=') else {
                continue;
            };
            let value = value.trim();
            match key.trim() {
                "skin" => chosen.skin = Some(value.to_string()),
                "cape" => chosen.cape = Some(value.to_string()),
                "model" => {
                    chosen.model = if value == "slim" {
                        Model::Slim
                    } else {
                        Model::Classic
                    }
                }
                _ => {}
            }
        }
        let exists = |kind, id: &Option<String>| {
            id.as_deref()
                .and_then(|id| self.path(kind, id))
                .is_some_and(|path| path.is_file())
        };
        if !exists(Kind::Skin, &chosen.skin) {
            chosen.skin = None;
        }
        if !exists(Kind::Cape, &chosen.cape) {
            chosen.cape = None;
        }
        chosen
    }

    pub fn save_selection(&self, chosen: &Selection) -> Result<(), String> {
        let mut text = String::new();
        if let Some(id) = chosen.skin.as_deref().filter(|id| valid_id(id)) {
            text += &format!("skin={id}\n");
        }
        if let Some(id) = chosen.cape.as_deref().filter(|id| valid_id(id)) {
            text += &format!("cape={id}\n");
        }
        text += match chosen.model {
            Model::Classic => "model=classic\n",
            Model::Slim => "model=slim\n",
        };
        fs::create_dir_all(&self.root).map_err(|e| format!("{}: {e}", self.root.display()))?;
        let to = self.root.join("selection.txt");
        write_atomically(&to, text.as_bytes()).map_err(|e| format!("{}: {e}", to.display()))
    }

    /// Wears a saved picture, or nothing (`None`: the default skin or no cape).
    pub fn select(&self, kind: Kind, id: Option<&str>) -> Result<(), String> {
        if let Some(id) = id
            && !self.path(kind, id).is_some_and(|path| path.is_file())
        {
            return Err(format!("That {} is no longer saved.", kind.word()));
        }
        let mut chosen = self.selection();
        match kind {
            Kind::Skin => chosen.skin = id.map(str::to_string),
            Kind::Cape => chosen.cape = id.map(str::to_string),
        }
        self.save_selection(&chosen)
    }

    pub fn set_model(&self, model: Model) -> Result<(), String> {
        let mut chosen = self.selection();
        chosen.model = model;
        self.save_selection(&chosen)
    }

    /// Deletes a saved picture; if it was worn, the default skin (or no cape) is worn again.
    pub fn remove(&self, kind: Kind, id: &str) -> Result<(), String> {
        let path = self.path(kind, id).ok_or("Not a saved picture.")?;
        match fs::remove_file(&path) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(format!("{}: {e}", path.display())),
        }
        let mut chosen = self.selection();
        let worn = match kind {
            Kind::Skin => &mut chosen.skin,
            Kind::Cape => &mut chosen.cape,
        };
        // `selection` already dropped the deleted file; this only rewrites the record.
        *worn = worn.take().filter(|worn| worn != id);
        self.save_selection(&chosen)
    }

    /// The files the game should draw now.
    pub fn worn(&self) -> Worn {
        let chosen = self.selection();
        let file = |kind, id: &Option<String>| id.as_deref().and_then(|id| self.path(kind, id));
        Worn {
            skin: file(Kind::Skin, &chosen.skin),
            cape: file(Kind::Cape, &chosen.cape),
            slim: chosen.model == Model::Slim,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store(name: &str) -> (Store, PathBuf) {
        let root = std::env::temp_dir().join(format!("dressing-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        (Store::new(&root), root)
    }

    #[test]
    fn the_same_picture_is_kept_once_and_different_ones_apart() {
        let (store, root) = store("dedupe");
        let a = store.add(Kind::Skin, b"first picture").unwrap();
        assert_eq!(store.add(Kind::Skin, b"first picture").unwrap(), a);
        let b = store.add(Kind::Skin, b"second picture").unwrap();
        assert_ne!(a, b);
        assert_eq!(store.list(Kind::Skin).len(), 2);
        // A skin and a cape with the same bytes are separate files.
        store.add(Kind::Cape, b"first picture").unwrap();
        assert_eq!(store.list(Kind::Cape).len(), 1);
        assert_eq!(store.read(Kind::Skin, &a).unwrap(), b"first picture");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn nothing_leaves_a_part_file_and_limits_are_enforced() {
        let (store, root) = store("limits");
        for i in 0..MAX_CAPES {
            store
                .add(Kind::Cape, format!("cape {i}").as_bytes())
                .unwrap();
        }
        let error = store.add(Kind::Cape, b"one too many").unwrap_err();
        assert!(error.contains("remove one first"), "{error}");
        // Saving a picture that is already kept still works at the limit.
        assert!(store.add(Kind::Cape, b"cape 3").is_ok());
        assert!(store.add(Kind::Skin, &[]).is_err());
        assert!(store.add(Kind::Skin, &vec![0; MAX_BYTES + 1]).is_err());
        let parts = fs::read_dir(root.join("capes"))
            .unwrap()
            .flatten()
            .filter(|e| e.file_name().to_string_lossy().ends_with(".part"))
            .count();
        assert_eq!(parts, 0);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn the_selection_survives_a_restart_and_never_names_a_missing_file() {
        let (store, root) = store("selection");
        assert_eq!(store.selection(), Selection::default());
        assert_eq!(store.worn(), Worn::default());
        let skin = store.add(Kind::Skin, b"skin bytes").unwrap();
        let cape = store.add(Kind::Cape, b"cape bytes").unwrap();
        store.select(Kind::Skin, Some(&skin)).unwrap();
        store.select(Kind::Cape, Some(&cape)).unwrap();
        store.set_model(Model::Slim).unwrap();
        // A fresh Store over the same folder is the next launch.
        let again = Store::new(&root);
        assert_eq!(
            again.selection(),
            Selection {
                skin: Some(skin.clone()),
                cape: Some(cape.clone()),
                model: Model::Slim
            }
        );
        let worn = again.worn();
        assert_eq!(worn.skin, again.path(Kind::Skin, &skin));
        assert!(worn.skin.as_ref().unwrap().is_file());
        assert!(worn.slim);
        // The file vanishes (storage cleared, SD card out): back to the default skin.
        fs::remove_file(worn.skin.unwrap()).unwrap();
        let after = Store::new(&root);
        assert_eq!(after.selection().skin, None);
        assert_eq!(after.selection().cape, Some(cape));
        assert_eq!(after.worn().skin, None);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn removing_a_worn_skin_falls_back_and_unknown_ids_are_refused() {
        let (store, root) = store("remove");
        let skin = store.add(Kind::Skin, b"worn skin").unwrap();
        store.select(Kind::Skin, Some(&skin)).unwrap();
        store.remove(Kind::Skin, &skin).unwrap();
        assert!(store.list(Kind::Skin).is_empty());
        assert_eq!(store.selection().skin, None);
        assert_eq!(store.worn().skin, None);
        // Removing twice is fine; a deleted or invented id cannot be worn.
        store.remove(Kind::Skin, &skin).unwrap();
        assert!(store.select(Kind::Skin, Some(&skin)).is_err());
        assert!(store.select(Kind::Skin, Some("../../etc/passwd")).is_err());
        assert!(store.remove(Kind::Skin, "../x").is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn a_hand_edited_selection_cannot_escape_the_folder() {
        let (store, root) = store("escape");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("secret.png"), b"x").unwrap();
        fs::write(
            root.join("selection.txt"),
            "skin=../secret\ncape=/etc/passwd\nmodel=slim\nnonsense\n",
        )
        .unwrap();
        let chosen = store.selection();
        assert_eq!((chosen.skin, chosen.cape), (None, None));
        assert_eq!(chosen.model, Model::Slim);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn newest_pictures_list_first() {
        let (store, root) = store("order");
        let old = store.add(Kind::Skin, b"old").unwrap();
        let file = store.path(Kind::Skin, &old).unwrap();
        let handle = fs::File::options().write(true).open(&file).unwrap();
        handle
            .set_modified(SystemTime::now() - std::time::Duration::from_secs(3600))
            .unwrap();
        let new = store.add(Kind::Skin, b"new").unwrap();
        assert_eq!(store.list(Kind::Skin), vec![new, old]);
        let _ = fs::remove_dir_all(root);
    }
}
