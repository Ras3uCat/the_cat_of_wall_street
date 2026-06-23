# Ras3uCat Brand Kit
### Identity System v1.0 — `EBrand.style`: Retro-Futuristic Tactical

> "Every build should feel like it was deployed from a futuristic command console
> with a quiet glowing mark in the corner: M3OW"

---

## Core Identity

| Field | Value |
| :--- | :--- |
| Brand Name | `Ras3uCat` |
| Stylized | `RAS3UCAT` |
| Catchphrase / Sigil | `M3OW` |
| Style | Retro-Futuristic Tactical |
| Credit Line | `D3V × Ras3uCat` |
| Footer Mark | `Sync complete △ M3OW` |
| Voice Tagline | `Designed to engage. Engineered to move. Deployed to perform.` |
| Deploy Line | `D3ploy with Ras3uCat.` |

---

## 1. Color System

The palette is built around a dark tactical environment lit by neon signals.
Never use pure white for text — always use `cyanTintedWhite`.

| Token | Hex | Usage |
| :--- | :--- | :--- |
| `EColors.primary` | `#58E3EF` | P-Cyan — primary actions, outlines, borders, focus states |
| `EColors.accent` | `#D34CF1` | A-Magenta — hover states, highlights, energy moments |
| `EColors.backgroundDark` | `#000612` | Midnight-Base — primary background |
| `EColors.circuitSlate` | `#1A1C2C` | Circuit-Slate — cards, panels, surface containers |
| `EColors.gold` | `#FFB938` | M3OW-Gold — sigil text, badges, special emphasis only |
| `EColors.cyanTintedWhite` | `#E8FEFF` | Body text — never use pure white (`#FFFFFF`) |

### Color Rules
- **Primary (P-Cyan)** is the default for all outlines, borders, and interactive elements.
- **Accent (A-Magenta)** is used sparingly — hover states, active sigils, energy moments only.
- **Gold** appears only with `M3OW` sigil marks or special highlights. Do not overuse.
- **Opacity usage:** 0.1 = subtle glow · 0.3 = borders · 0.5 = secondary text · 0.7 = overlays · 0.8 = emphasis

---

## 2. Typography

Four font families. Each has a specific role. Do not swap them.

| Role | Font | Constant | Usage |
| :--- | :--- | :--- | :--- |
| Headlines | **Play** | `GoogleFonts.play` | Hero headings, section titles |
| Headlines Alt | **Orbitron** | `GoogleFonts.orbitron` | Futuristic system tone, secondary headings |
| Interface / UI | **Space Grotesk** | `GoogleFonts.spaceGrotesk` | Labels, tags, UI copy, sigil text |
| Body | **Inter** | `GoogleFonts.inter` | Descriptions, readable copy |

### Type Rules
- Headlines: **uppercase** or wide letter-spacing (`letterSpacing: 3.0–4.0`).
- Body: clean, readable, low contrast (`EColors.cyanTintedWhite` at 0.8 opacity for secondary).
- Numbers: use tabular or monospace variants where possible.
- Neon glow: apply 3-layer text shadow (blur 3, 6, 9px) using `EColors.primary` — see `NeonText` widget.

---

## 3. Visual Tone — Geometric Wired-Frame

Ras3uCat interfaces are constructed like digital skeletons: visible structure, minimal fill, maximum intent.

### Core Rules

**Hollow Geometry**
- Use `PaintingStyle.stroke` over `PaintingStyle.fill` wherever possible.
- Base stroke width: `1.0`. Max: `1.5` for brand marks.
- Favor triangles, angled lines, and hex-like structures.

**Dynamic Glow**
- Active or hover elements use: `MaskFilter.blur(BlurStyle.normal, 3)`
- Glow layer: 30% opacity of the element color, stroke width +2, blur 3.5px.
- Never apply glow to static/idle elements — it must be earned by interaction.

**Micro-Gradients**
- Use subtle depth, never heavy fills.
- Gradient stop pattern: `[0.0 → opacity 0.1] [0.4 → opacity 0.5] [1.0 → full color]`
- See `TrianglePainter` for the established gradient implementation.

**Geometry Motifs (use consistently)**
- Triangles — primary motif
- Wireframe pyramids
- Node connections
- Grid overlays

---

## 4. Motion Language

Motion should feel like systems activating, not playful UI.

### Approved Motions
| Motion | Implementation |
| :--- | :--- |
| Parallax drift | Tie position offset to `EScrollController.scrollOffset` |
| Scroll entrance | Wrap with `AnimatedOnView`, `startOffset: Offset(0, 50)`, 600ms |
| Gradient shimmer | `GradientOverlay` widget + `GradientController` |
| Triangle rotation | `TriangleController.animationController` (20s loop) |
| Button hover | 300ms color/shadow transition via `EDurations.buttonHover` |
| Neon pulse | Optional 6–8s pulse on sigil marks only |

### Avoid
- Bounce animations
- Elastic motion / spring curves
- Cartoon easing (`Curves.elasticOut`, `Curves.bounceIn`)
- Chaotic or unpredictable movement

### Timing Tokens
| Token | Value | Use |
| :--- | :--- | :--- |
| `EDurations.pageTransition` | 500ms | Route changes |
| `EDurations.animationOnView` | 600ms | Scroll entrance animations |
| `EDurations.buttonHover` | 300ms | Hover state transitions |

---

## 5. Components

### Buttons — `NeonButton`
- **Default:** Transparent fill, 2px cyan border (`EColors.primary` at 0.8 opacity).
- **Hover:** Magenta border (`EColors.accent`), gradient overlay, accent glow shadow.
- **Tap:** Cyan splash, 0.1 highlight opacity.
- Never use filled/solid buttons. Outline only.

### Text — `NeonText`
- 3-layer shadow blur (3, 6, 9px) for glow effect.
- Default color: `EColors.primary`. Accent moments: `EColors.accent`.
- Headlines: `isHeadline: true` — auto-sizes proportionally.

### Cards — `ProjectCard`
- 1px cyan border at 0.3 opacity.
- Dark gradient background (near-transparent to full midnight).
- Cyan glow box shadow (0.1 opacity, 5px blur).
- Corner detail: consistent with the wireframe geometric aesthetic.

### Dialogs — `EDialog`
- Semi-transparent dark background (`EColors.backgroundDark` at 0.7 opacity).
- 2px cyan border, `borderRadius: 32`.
- Responsive margins: mobile 10% · tablet 20% · desktop 30%.

### Progress / Segmented Elements
- Never smooth fill. Always segmented blocks.
- Example pattern: `[■■■□□□■■■□□]`

---

## 6. Brand Sigil — M3OW

`M3OW` is not just text. It is a functional brand mark.

### Variants
| Variant | Value | Context |
| :--- | :--- | :--- |
| `EBrand.sigilPrimary` | `M3OW` | General use, footer, badge |
| `EBrand.sigilMono` | `[M3OW]` | Terminal output, debug messages, CLI |
| `EBrand.sigilGlowing` | `✦ M3OW` | Emphasis, loading sequences, easter eggs |

### Credit Lines
| Variant | Value |
| :--- | :--- |
| `EBrand.creditPrimary` | `D3V × Ras3uCat` |
| `EBrand.creditTriangle` | `△ D3V × Ras3uCat` |
| `EBrand.creditCompact` | `D3V×Ras3uCat` |

### Sigil Widget — `M3OWBrandMark`
- Custom-painted geometric mark. Use `size` param to scale.
- Default color: `EColors.primary`. Gold variant: `EColors.gold`.
- Use `EColors.gold` only in footer/badge contexts.
- Recommended sizes: `24` (sm), `48` (md), `96` (lg).

### Usage Rules
- Sigil appears in: footers, loading sequences, tooltips (easter eggs), terminal-style outputs.
- Closing mark on all brand-authored content: `EBrand.voiceFooter` → `Sync complete △ M3OW`

---

## 7. Image Usage

### Logo Variants
| File | Background | Usage |
| :--- | :--- | :--- |
| `raspucat_black.svg` | Light / white bg | Light theme contexts |
| `raspucat_white.svg` | Dark / midnight bg | Primary usage on the site |
| `raspucat_gradient.png` | Any | Promotional, hero moments |
| `raspucat_512.png` | Any | App icon, favicon |

### Logo Rules
- Always wrap the logo in `GradientOverlay` for on-brand display.
- Size: 50% of the shorter viewport dimension (`min(width, height) * 0.5`).
- Use `BoxFit.contain`. Never stretch or crop.
- Never place the logo on a light background without using the black SVG variant.

### Project / Content Images
- **Always** apply a cyan overlay tint: `Color(EColors.primary.value).withOpacity(0.1)`.
- Use a gradient placeholder (primary → secondary, 0.2 opacity each) when image is loading.
- Max display size for cards: `ESizes.imageSizeXl` (300px height).

---

## 8. Brand Voice

**Tone:** Technical · Confident · Precise · Slightly mysterious

### Do
- `We engineer precision digital systems.`
- `D3ploy with Ras3uCat.`
- `Sync complete △ M3OW`
- `Designed to engage. Engineered to move. Deployed to perform.`

### Don't
- ~~"We build awesome apps"~~
- ~~"Let's work together"~~
- ~~"Simple and easy to use"~~
- ~~Generic startup language or corporate buzzwords~~

### Voice Tokens (`EBrand`)
| Constant | Value |
| :--- | :--- |
| `EBrand.voiceTagline` | `Designed to engage. Engineered to move. Deployed to perform.` |
| `EBrand.voiceDeploy` | `D3ploy with Ras3uCat.` |
| `EBrand.voiceFooter` | `Sync complete △ M3OW` |

---

## 9. Explorability Principles

Ras3uCat interfaces reward curiosity.

- **Hidden interactions:** Triangles respond to hover (scale 1.2x) and tap (respawn).
- **Easter eggs:** Sigil appears in unexpected places — tooltips, terminal outputs, loading states.
- **Depth:** Parallax layers create spatial depth without 3D rendering.
- **Scroll events:** Every major section entrance is animated via `AnimatedOnView`.
- **Mouse feedback:** `MouseRegion` hover on interactive elements; never static on desktop.
- **The brand kit itself** is a hidden route — `/brand-kit` — discoverable by URL only.

---

*`Sync complete △ M3OW`*
