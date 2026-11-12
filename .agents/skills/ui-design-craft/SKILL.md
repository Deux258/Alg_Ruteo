---
name: ui-design-craft
description: Unified frontend design system combining ui-ux-pro-max (nextlevelbuilder), taste-skill (Leonxlnx), impeccable (pbakaus), and apple-design (emilkowalski) for mission-control, geospatial, and 3D web interfaces.
---

# UI Design Craft (UI/UX Pro Max + Taste + Impeccable + Apple Design)

This skill synthesizes four complementary design engineering frameworks for building and refining high-craft interfaces:

## 1. Apple Design (`emilkowalski/skills` — `apple-design`)
- **Zero Perceived Latency**: Controls respond immediately on `pointerdown` / `:active` (`transform: scale(0.985)` with `transition-duration: 60ms` on press) and recover with spring-like physics (`cubic-bezier(0.22, 1, 0.36, 1)`).
- **Interruptible Transitions**: Use CSS transitions on transform, opacity, background, and box-shadow rather than blocking keyframes so mid-gesture changes smoothly retarget.
- **Materials & Depth**: Floating HUDs, players, and map overlays use translucent materials (`backdrop-filter: blur(16px) saturate(180%)`), subtle inner specular highlights (`inset 0 1px 0 rgba(255,255,255,0.65)`), and layered ambient/contact shadows.
- **Optical Typography & Tabular Numerals**: Tight tracking on headings (`-0.02em` to `-0.03em`), generous line-height on body copy, and `font-variant-numeric: tabular-nums` on all live telemetry, timers, coordinates, and metrics.

## 2. Impeccable (`pbakaus/impeccable` — `Operate / Read` Mode)
- **Precision & Scanability**: For mission-control and analytical dashboards, prioritize clear visual hierarchy, grouped bento metric cells, scannable status badges, and unmistakable active/selected states.
- **Hardened Responsiveness**: Guarantee zero horizontal overflow (`scrollWidth <= innerWidth`) across desktop (`1440x1000+`) and mobile (`390x844`) viewports.

## 3. Taste Skill (`Leonxlnx/taste-skill` — Anti-Slop Art Direction)
- **Domain-Authentic Color & Contrast**: Avoid generic SaaS purple/neon gradients. Use cohesive, domain-grounded palettes (deep forest obsidian, warm cartographic alabaster, botanical emerald, and terracotta hazard accents).
- **Avionics-Grade Telemetry**: Style flight logs, coordinates, and HUD overlays as high-contrast monospace readouts with crisp hairlines.

## 4. UI/UX Pro Max (`nextlevelbuilder/ui-ux-pro-max-skill`)
- **Design Tokens**: Centralize colors, radii, shadows, and easing curves in `:root`.
- **Accessibility & Focus**: Provide high-contrast `:focus-visible` outlines, clear disabled states, and readable popup rows.
