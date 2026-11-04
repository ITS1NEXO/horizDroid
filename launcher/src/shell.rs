//! The launcher's frame in the night look (docs/design-system.md, "Night"): the sidebar's plate
//! and rows, and the top bar's tabs, icon buttons and account chip. The sky shows between them;
//! only the sidebar and the selected or hovered parts are plates.
use crate::plate::alpha;
use crate::theme::{self, night, Step, Theme};
use crate::{hover_fade, keyboard, track_hover};
use gpui::{div, prelude::*, px, rgb, Div, FontWeight, Hsla, SharedString, Stateful};

/// A night colour as GPUI's.
pub fn c(color: u32) -> Hsla {
    rgb(color).into()
}

/// Text in one of the night's type steps (`night::TYPE`), at its own weight.
pub fn text(step: Step, color: Hsla) -> Div {
    div()
        .font_family(if step.px >= night::DISPLAY.px {
            theme::DISPLAY_FONT
        } else {
            theme::FONT
        })
        .font_weight(FontWeight(step.weight as f32))
        .text_size(px(step.px))
        .line_height(px(step.line_px()))
        .text_color(color)
}

/// The sidebar's ground: `card` at its opacity from the top of the window to the bottom, with a
/// 1 px stroke on its right edge. Square: it meets the window's edges.
pub fn sidebar_plate(t: &Theme) -> Div {
    let n = t.night;
    div()
        .bg(alpha(n.card, n.card_alpha))
        .border_r_1()
        .border_color(alpha(n.stroke, n.stroke_alpha))
}

/// A softly rounded plate behind a selected row or tab.
fn selected(_steps: usize, t: &Theme) -> Div {
    let n = t.night;
    div()
        .absolute()
        .top_0()
        .left_0()
        .size_full()
        .rounded(px(8.))
        .bg(alpha(n.card_hi, n.card_hi_alpha))
        .border_1()
        .border_color(alpha(n.stroke, n.stroke_alpha * 1.5))
}

/// The same rounded surface, fading in while the pointer is over `id`.
fn hovered(id: &SharedString, steps: usize, t: &Theme) -> gpui::AnyElement {
    let n = t.night;
    let layer = move || {
        div()
            .absolute()
            .top_0()
            .left_0()
            .size_full()
            .rounded(px(8.))
            .bg(alpha(n.card_hi, n.card_hi_alpha * 0.5))
    };
    hover_fade(id, layer, |d, a| d.opacity(a))
}

/// A sidebar row (an instance, a server): its picture and two lines go in as children. The
/// selected one sits on a plate cut in two steps; the others get one while hovered.
pub fn row(id: impl Into<SharedString>, selected_now: bool, t: &Theme) -> Stateful<Div> {
    let id = id.into();
    let d = div()
        .id(id.clone())
        .relative()
        .flex()
        .items_center()
        .gap(px(12.))
        .h(px(52.))
        .px(px(8.))
        .cursor_pointer();
    let d = if selected_now {
        d.child(selected(2, t))
    } else {
        d.child(hovered(&id, 2, t))
    };
    keyboard(track_hover(d, id), t)
}

/// A row's two lines: the name, and its state after a small square in `state`'s colour when it
/// has one ("Ready · 26.3" in green, "Needs preparing" in amber).
pub fn row_text(name: impl Into<SharedString>, sub: String, state: Option<Hsla>, t: &Theme) -> Div {
    let n = t.night;
    div()
        .relative()
        .flex()
        .flex_col()
        .min_w_0()
        .child(
            text(night::UI, c(n.ink))
                .font_weight(FontWeight::SEMIBOLD)
                .truncate()
                .child(name.into()),
        )
        .child(
            div()
                .flex()
                .items_center()
                .gap(px(6.))
                .min_w_0()
                .children(state.map(|s| div().flex_none().size(px(6.)).bg(s)))
                .child(text(night::CAPTION, c(n.muted)).truncate().child(sub)),
        )
}

/// A heading over a group of rows ("Instances", a group's name, "Servers"), with room for a
/// button on its right.
pub fn heading(label: impl Into<SharedString>, t: &Theme) -> Div {
    div()
        .flex()
        .items_center()
        .justify_between()
        .h(px(32.))
        .px(px(8.))
        .mt(px(8.))
        .child(
            text(night::CAPTION, c(t.night.muted))
                .font_weight(FontWeight::SEMIBOLD)
                .child(label.into()),
        )
}

/// A page's tab in the top bar: its name, on a plate cut in one step while it is the page shown.
pub fn tab(id: impl Into<SharedString>, label: &str, active: bool, t: &Theme) -> Stateful<Div> {
    let id = id.into();
    let n = t.night;
    let d = div()
        .id(id.clone())
        .relative()
        .flex()
        .items_center()
        .h(px(32.))
        .px(px(14.))
        .cursor_pointer();
    let d = if active {
        d.child(selected(1, t))
    } else {
        d.child(hovered(&id, 1, t))
    };
    keyboard(
        track_hover(
            d.child(
                text(night::UI, c(if active { n.ink } else { n.ink_soft }))
                    .relative()
                    .child(label.to_string()),
            ),
            id,
        ),
        t,
    )
}

/// A square button with one icon (Settings, the sidebar's `+`), cut in one step.
pub fn icon_button(
    id: impl Into<SharedString>,
    icon: &'static str,
    size: f32,
    active: bool,
    t: &Theme,
) -> Stateful<Div> {
    let id = id.into();
    let n = t.night;
    let d = div()
        .id(id.clone())
        .relative()
        .flex()
        .flex_none()
        .items_center()
        .justify_center()
        .size(px(size))
        .cursor_pointer();
    let d = if active {
        d.child(selected(1, t))
    } else {
        d.child(hovered(&id, 1, t))
    };
    keyboard(
        track_hover(
            d.child(div().relative().child(crate::blocks::icon(
                icon,
                (size * 0.5).round(),
                c(if active { n.ink } else { n.ink_soft }),
            ))),
            id,
        ),
        t,
    )
}

/// The account chip's plate: `card` cut in one step with its stroke, for the picture and two
/// lines that go in as children.
pub fn chip(id: impl Into<SharedString>, t: &Theme) -> Stateful<Div> {
    let id = id.into();
    let n = t.night;
    let d = div()
        .id(id.clone())
        .relative()
        .flex()
        .min_w_0()
        .items_center()
        .gap(px(10.))
        .h(px(40.))
        .pl(px(6.))
        .pr(px(12.))
        .cursor_pointer()
        .child(
            div()
                .absolute()
                .top_0()
                .left_0()
                .size_full()
                .rounded(px(10.))
                .bg(alpha(n.card, n.card_alpha))
                .border_1()
                .border_color(alpha(n.stroke, n.stroke_alpha)),
        )
        .child(hovered(&id, 1, t));
    keyboard(track_hover(d, id), t)
}

/// A launcher button: the main action, a raised secondary action, or a quiet text action.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Main,
    Raised,
    Quiet,
}

/// A consistent rounded launcher button. Icons and the label go in as children.
pub fn action(id: impl Into<SharedString>, kind: Action, t: &Theme) -> Stateful<Div> {
    let id = id.into();
    let n = t.night;
    let d = div()
        .id(id.clone())
        .relative()
        .flex()
        .flex_none()
        .items_center()
        .justify_center()
        .gap(px(10.))
        .px(px(16.))
        .font_family(theme::FONT)
        .font_weight(FontWeight::MEDIUM)
        .text_size(px(night::UI.px))
        .cursor_pointer();
    let fill = |d: Div| d.absolute().top_0().left_0().size_full();
    let round = move || fill(div()).rounded(px(8.));
    let d = match kind {
        Action::Main => d
            .h(px(night::PLAY))
            .px(px(28.))
            .text_size(px(night::TITLE.px))
            .font_weight(FontWeight::BOLD)
            .text_color(c(n.on_accent))
            .child(fill(div().rounded(px(8.)).bg(alpha(n.accent, 1.))))
            .child(hover_fade(
                &id,
                move || {
                    fill(div().rounded(px(8.)).bg(alpha(n.on_accent, 0.12)))
                },
                |d, a| d.opacity(a),
            )),
        Action::Raised => d
            .h(px(theme::CONTROL))
            .rounded(px(night::RADIUS_CONTROL))
            .bg(alpha(n.card_hi, n.card_hi_alpha))
            .border_1()
            .border_color(alpha(n.stroke, n.stroke_alpha))
            .text_color(c(n.ink))
            .child(hover_fade(&id, round, move |d, a| {
                d.bg(alpha(n.ink, 0.06 * a))
            })),
        Action::Quiet => d
            .h(px(theme::CONTROL))
            .rounded(px(night::RADIUS_CONTROL))
            .text_color(c(n.ink_soft))
            .child(hover_fade(&id, round, move |d, a| {
                d.bg(alpha(n.card_hi, n.card_hi_alpha * 0.5 * a))
            })),
    };
    keyboard(track_hover(d, id), t).active(|s| s.opacity(theme::PRESSED))
}

/// A label for an [`action`], over its hover layer.
pub fn label(text_: impl Into<SharedString>) -> Div {
    div().relative().child(text_.into())
}
