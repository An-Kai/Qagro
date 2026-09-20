---
name: swiss-web-design
description: >
  Use when building or reviewing websites in the Swiss Style / International
  Typographic tradition — cargo.site portfolios, Wayfinder-style brand sites,
  and European modernist web design. Emphasises grid systems, typographic
  hierarchy, asymmetric composition, and whitespace as an active material.
  Framed for graphic designers directing web output, not frontend developers.
  Trigger words: Swiss, cargo.site, Wayfinder, modernist, grid system,
  Helvetica, International Typographic Style, graphic designer portfolio.
---

# Swiss Web Design

A design skill for building websites the way a graphic designer would —
composing with type, grid, and space rather than components, state, and
breakpoints. This skill covers three overlapping traditions:

- **Swiss Style / International Typographic Style** — the 1950s movement
  (Müller-Brockmann, Ruder, Hofmann, Bill) that made grids, sans-serif
  typography, and asymmetric balance the lingua franca of modern design.
- **Cargo.site** — the contemporary portfolio platform for designers and
  artists who refuse template-looking templates. Cargo's constraint model
  (pinned pages, overlaid layers, image-centric grids) rewards a Swiss
  approach.
- **Wayfinder Design** — a 2020s evolution that pushes Swiss rigour into
  dark-canvas, ultra-thin type, path-based typographic illustration, and
  asynchronous gradients. Think black backgrounds, weight-300 display faces,
  and 0.042em tracking.

---

## Table of Contents

1. Philosophy
2. Grid Systems
3. Typography as Interface
4. Whitespace as Material
5. Colour
6. Photography over Illustration
7. Asymmetric Composition
8. Cargo.site Patterns
9. Wayfinder Design Patterns
10. CSS Framework / Design Tokens
11. Spacing Scale
12. Responsive Behaviour
13. Key Historical References
14. Contemporary Reference Sites
15. Design Review Checklist
16. Poster-to-Web Translation
17. Brutalist Web Design
18. Texture & Material
19. Editorial / Magazine Layout
20. Image Analysis & Design Extraction

---

## 1. Philosophy

Swiss Style is not a look — it is a method. Six principles govern every
decision:

| Principle | Meaning |
|-----------|---------|
| **Form follows function** | Every element earns its place by doing work. If it does not communicate, remove it. |
| **Clarity before expression** | The viewer must understand before they admire. Design succeeds when it stops needing interpretation. |
| **Reduction** | Perfection is achieved not when there is nothing left to add, but when there is nothing left to take away. |
| **Objectivity** | Personal taste is subordinate to the message. Neutrality makes the design a vehicle, not a destination. |
| **Mathematics** | Proportion, scale, and alignment follow rational systems — grids, ratios, modular scales — not intuition. |
| **Typography is the interface** | Type does the work that chrome, shadows, and illustrations do elsewhere. The page is a typographic composition. |

When making decisions, ask: *Does this help someone understand something
faster?* If the answer is no, remove it.

---

## 2. Grid Systems

The grid is the backbone. Müller-Brockmann called it *"a system of order that
makes the message more easily understood."* It is not a cage — it is an
instrument. By settling the boring decisions in advance, it frees you to spend
judgment on what matters.

### Modular Grid — 12 Columns

```css
.swiss-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: var(--grid-gap, 20px);
  max-width: var(--max-width, 1200px);
  margin: 0 auto;
  padding: 0 var(--spacing-6, 32px);
}
```

- **12 columns** gives maximum flexibility: 1/12, 2/12, 3/12 … 12/12.
- **Gap** is fixed at 20px (or 1.25rem). Gutter is the same across the whole
  system — never use margin on individual items.
- **Max-width** 1200px or 960px for tighter typographic measure.
- **Baseline grid** 8px increments. Every margin, padding, and height is a
  multiple of 8 (or 4 for fine adjustments).

### Asymmetric Column Spans

Swiss layouts rarely use equal columns. A typical hero:

```
|          |              |     |
|  logo    |  headline    | nav |
|  2 cols  |  6 cols      | 4   |
```

Content sections vary:

```
|  headline — 8 cols   | empty — 4 cols |
| body text — 5 cols   | image — 7 cols |
| image — 12 cols (full-bleed)          |
```

Grid column assignment should vary per section. Never repeat the same grid
template for every row — that is not a Swiss grid, it is a spreadsheet.

### Cargo-Specific Grid Notes

Cargo 3 uses a freeform coordinate system rather than a strict CSS grid, but
the same principles apply:

- Set **Page Width** to a percentage (80–92%) rather than a pixel value.
- Use **Pinned** pages for persistent navigation overlays.
- Use **Stacked** pages for scroll-based content sections.
- Custom CSS overrides should only adjust the Cargo grid when the template
  forces symmetry you do not want. Inject overrides in the custom CSS panel:

```css
.page {
  max-width: 1200px;
  margin: 0 auto;
}
```

---

## 3. Typography as Interface

Swiss designers did not decorate with type — they built with it. Emil Ruder
argued that legibility and visual rhythm are inseparable. On most pages, type
*is* the interface. Strip away the images and the gradients and what is left is
text doing the work.

### Typeface Selection

| Use | Primary | Fallback Stack |
|-----|---------|----------------|
| Display / UI | Inter | `'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif` |
| Display / UI (alt) | Helvetica Neue | `'Helvetica Neue', Helvetica, Arial, sans-serif` |
| Classic Swiss | Akzidenz-Grotesk | `'Akzidenz-Grotesk', 'Helvetica Neue', Helvetica, Arial, sans-serif` |
| Wayfinder-style | Enreal (or substitute) | `'Enreal', 'Jost Light', 'DM Sans Light', 'Outfit Light', 'Helvetica Neue', Helvetica, Arial, sans-serif` |
| Mono (code / data) | JetBrains Mono | `'JetBrains Mono', 'SF Mono', 'Fira Code', monospace` |

Rules:
- **One family. Two weights. Three sizes.** Never use more than one typeface
  family (except mono for data).
- **No serifs.** Ever. Garamond, Caslon, Times — all forbidden.
- **No decorative fonts.** The typeface must be neutral, well-drawn, and
  invisible. The message, not the font, is what should be noticed.

### Modular Type Scale

Use a consistent ratio. Perfect fourth (1.25) or augmented fourth (1.333):

```css
:root {
  /* Perfect fourth scale (1.25) */
  --font-size-xs:   0.75rem;   /* 12px */
  --font-size-sm:   0.875rem;  /* 14px */
  --font-size-base: 1rem;      /* 16px */
  --font-size-md:   1.25rem;   /* 20px */
  --font-size-lg:   1.563rem;  /* 25px */
  --font-size-xl:   1.953rem;  /* 31px */
  --font-size-2xl:  2.441rem;  /* 39px */
  --font-size-3xl:  3.052rem;  /* 49px */
  --font-size-4xl:  3.815rem;  /* 61px */
  --font-size-5xl:  4.768rem;  /* 76px */
}
```

### Weight Distribution

| Token | Value | Used For |
|-------|-------|----------|
| `--font-weight-light` | 300 | Display headlines, Wayfinder-style titles |
| `--font-weight-regular` | 400 | Body text, labels |
| `--font-weight-medium` | 500 | UI labels, captions, buttons |
| `--font-weight-bold` | 700 | Headings, emphasis |

Swiss design uses weight as a **structural tool**, not decoration. Bold
headings are bold because the content hierarchy demands it, not because bold
looks nice.

### Line Height

| Role | Line Height | Notes |
|------|-------------|-------|
| Headings / Display | 1.0 – 1.1 | Tight for impact |
| Body text | 1.4 – 1.6 | Generous for readability |
| Captions / Meta | 1.2 | Compact |

### Letter Spacing (Tracking)

| Role | Tracking | Notes |
|------|----------|-------|
| Display (standard) | `-0.02em` | Tight for headlines |
| Body | `0` | Normal |
| UI Labels / Captions | `0.01em – 0.05em` | Slight looseness |
| Wayfinder display | `0.042em` | Wide — cinematic, breathing |
| Uppercase labels | `0.05em – 0.1em` | Deliberate, wide |

### Alignment

- **Flush left, ragged right.** Always. Justified text creates uneven rivers of
  whitespace. Centred text is reserved for specific compositional moments
  (Wayfinder-style title cards). Never right-align body text.
- **Left-align everything** on the grid. Logo, nav, headlines, body, captions.

### Measure (Line Length)

- Body text: **45–75 characters per line** (ideal: ~66).
- Constrain width on text-heavy sections:
  ```css
  max-width: 66ch;
  ```

### OpenType Features

Always enable standard ligatures and contextual alternates:

```css
body {
  font-feature-settings: "liga" 1, "calt" 1;
}
```

For Inter specifically, enable single-story `a` (`cv11`).

---

## 4. Whitespace as Material

Swiss designers treated empty space as a material to be shaped, not a void to
be filled. Müller-Brockmann composed his Tonhalle posters around the space as
deliberately as around the type.

### Spacing Philosophy

1. **Start with the space.** Begin the layout with generous whitespace and let
   content earn its way in.
2. **Double the gap.** Whatever padding or margin you think is right, double it
   before you halve it.
3. **The 20% rule.** Remove one-fifth of non-essential elements. What remains
   will breathe better.
4. **Don't fill the margins.** Resist the reflex to add a banner, a button, or
   a third image just because there is room.

### Section Gaps

```css
:root {
  --section-gap: clamp(4rem, 8vw, 8rem);
}
```

A headline given a full column of air reads as confident. The same headline
boxed in by three buttons and a banner reads as anxious. Nothing about the
headline changed — only what surrounds it.

---

## 5. Colour

Swiss colour is minimalist. The palette does the work of hierarchy and does
not compete with content.

### Core Palette

```css
:root {
  /* Greys */
  --color-black:       #1A1A1A;
  --color-dark:        #2D2D2D;
  --color-mid-grey:    #6A6A6A;
  --color-cool-grey:   #A9B2B1;
  --color-light-grey:  #E5E5E5;
  --color-off-white:   #F4F3EE;
  --color-white:       #FFFFFF;

  /* Accent — choose ONE */
  --color-accent:      #D82C2C;   /* signal red (classic Swiss) */

  /* Functional */
  --color-text-primary:   var(--color-black);
  --color-text-secondary: var(--color-mid-grey);
  --color-text-on-dark:   var(--color-white);
  --color-bg-primary:     var(--color-white);
  --color-bg-secondary:   var(--color-off-white);
  --color-bg-dark:        var(--color-black);
  --color-border:         var(--color-black);
}
```

### Rules

- **One accent colour maximum.** Red is the canonical Swiss accent.
  Occasionally blue (#2B5FD7) or yellow (#E8B82C) for specific brands.
- **Monochromatic + one accent.** Every other colour should be a grey.
- **No gradients unless Wayfinder.** Standard Swiss is flat colour.
  Wayfinder-style uses asynchronous gradients as a deliberate, system-level
  exception — not a decorative afterthought.
- **No drop shadows, no glow, no card layers.** Swiss design is flat. Depth
  comes from hierarchy, not from shadows.

### Wayfinder Expandida Palette

```css
:root {
  --color-void-black:       #000000;
  --color-smolder-earth:    #0B0502;
  --color-charcoal:         #1A1A1A;
  --color-bone-white:       #FFFFFF;
  --color-ash:              #E3E3E2;
  --color-driftwood:        #C0BFBE;
}
```

---

## 6. Photography over Illustration

Swiss Style favours photography because it is *objective* — it represents
reality without the designer's hand interposing.

### Guidelines

- **Use photography as the primary visual content.** Not illustration, not
  3D renders, not decorative iconography.
- **Full-bleed images** are the default. Let images reach the edge of the
  grid or the viewport.
- **Scale by width, not height.** Images should fill their container
  horizontally and crop vertically.
- **No drop shadows on images.** No rounded corners. No decorative frames.
- **Black-and-white or desaturated** photography reads as more objective and
  integrates better with typography.
- **Wayfinder exception:** illustration is allowed when it is the *entire
  viewport canvas* — a world the type floats on, not a decorative sidebar.

---

## 7. Asymmetric Composition

Swiss asymmetry is not chaos — it is dynamic balance. The eye moves from a
strong element to a quieter one, guided by the grid.

### Compositional Patterns

```
Pattern A: Off-centre hero
  [  empty (3)  |  headline (7)  |  nav (2)  ]

Pattern B: Split content
  [  body text (5)  |  image (7)  ]

Pattern C: Full-bleed interruption
  [  image (12) — full viewport width  ]

Pattern D: Wayfinder title card
  [  empty (4)  |  centred title (4)  |  empty (4)  ]
  Content vertically and horizontally centred in the viewport.

Pattern E: Three-column data
  [  stat (4)  |  stat (4)  |  stat (4)  ]
```

### Rules

- **No equal columns for content sections.** If every section is three equal
  columns, the design is not Swiss — it is a generic template.
- **One section can be asymmetric; the next can be full-bleed; the next can be
  a single centred column.** The grid unifies them.
- **Break the grid deliberately.** A full-bleed image, an oversized number, a
  red bar across all 12 columns — these read as intentional because the grid
  provides the baseline.

---

## 8. Cargo.site Patterns

Cargo is a site builder for designers and artists. Its templates reward a Swiss
approach because the platform itself is image-and-type-centric.

### Template Selection

- **Basic Grid** — good starting point for Swiss layouts. Gives you a
  column-based image grid you can customise.
- **Basic Feed** — single-column vertical scroll. Strong for typographic
  portfolios.
- **Blank** — full control. Start from a CSS grid you define.

### Key Cargo Features for Swiss Design

| Feature | Swiss Application |
|---------|-------------------|
| **Page Width** | Set 80–92%. Gives generous margins. |
| **Content Background** | Set to white or off-white. Page Background stays the same or slight tint. |
| **Page Border** | Thin black border (1–2px). Acts like a typographic rule framing the composition. |
| **Site Border** | Optional outer border. Creates a printed-page feeling. |
| **Pinned pages** | Use for persistent navigation sidebar or nameplate. |
| **Overlaid pages** | Creates depth — a background image page with a semi-transparent content page on top. |
| **Colour Filter** | Monochrome filter on images to unify the palette. |
| **Active Link style** | Bold weight or underline for current page in navigation. |

### Custom CSS Overrides for Cargo

```css
/* Typography refinements */
body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: #1A1A1A;
}

/* Remove forced image borders */
img {
  border-radius: 0 !important;
  box-shadow: none !important;
}

/* Strict Swiss Image Behaviours */
.cargo-image-zoom {
  pointer-events: none !important; /* Disable image zoom */
}
.cargo-image:hover, .thumbnails a:hover {
  filter: saturate(0.2) contrast(1.1) !important; /* Only colour changes for hover, no generic effects */
  transform: none !important;
}

/* Tighten navigation */
nav, .nav, [role="navigation"] {
  font-size: 14px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* Wider gutters */
.page {
  padding: 40px 32px;
}
```

### Cargo 2 vs Cargo 3

| | Cargo 2 | Cargo 3 |
|--|---------|---------|
| Layout | Column-bound, code-heavy | Freeform coordinates, visual canvas |
| Mobile | Global scaling (can break desktop) | Isolated mobile config |
| Best for | Complex custom grid overrides | Quick asymmetric layouts |
| Swiss fit | Good if you need strict grid control | Better for freeform Swiss asymmetry |

---

## 9. Wayfinder Design Patterns

Wayfinder (the SF-based venture fund rebrand by HEX.inc) represents a
contemporary evolution of Swiss principles into a dark, cinematic direction.

### Core Characteristics

| Element | Specification |
|---------|---------------|
| Canvas | Pure black (`#000000`). The black is a stage, not a background. |
| Display type | Weight 300 (ultra-thin), 0.042em tracking, all-caps or sentence case |
| Body type | Weight 400, same family |
| Composition | Vertically and horizontally centred in the viewport |
| UI | Icon-only, monochrome, no labels, no tooltips, no backgrounds |
| Illustration | Full-viewport illustration or animation — never cropped, never overlaid |
| Buttons | Filled white for primary action; dark outlined for secondary |
| Atmosphere | Cinematic, title-card quality. Every screen is a composed frame. |

### Design Tokens (Wayfinder Variant)

```css
:root {
  /* Typography */
  --font-display: 'Enreal', 'Jost Light', 'DM Sans Light', 'Outfit Light', ui-sans-serif, system-ui, sans-serif;
  --font-body:    'Enreal', 'Jost', 'DM Sans', ui-sans-serif, system-ui, sans-serif;

  --text-display: clamp(3rem, 5vw, 4rem);
  --text-subtitle: 14px;
  --text-body: 16px;
  --text-caption: 13px;

  --tracking-display: 0.042em;
  --tracking-body: 0.67px;

  --leading-display: 1.0;
  --leading-body: 1.2;

  /* Colours */
  --color-bg: #000000;
  --color-text: #FFFFFF;
  --color-text-muted: rgba(255, 255, 255, 0.7);
  --color-border: #333333;
}
```

### When to Use Wayfinder vs Standard Swiss

| Context | Approach |
|---------|----------|
| Portfolio site, light background | Standard Swiss |
| Brand site, dark / tech / premium | Wayfinder-inspired |
| Full-screen experience | Wayfinder |
| Content-heavy reading site | Standard Swiss |
| Art / experimental | Either, leaning Wayfinder |

### Decorative Symbols (Wayfinder & Metro)

Modernist wayfinding design heavily utilizes geometric and functional symbols rather than illustrative icons. These should be set in-line with display text or used in background layouts as framing devices.

#### Arrow Set (Directional Navigation)
- `→` Arrow Right (Standard navigation / button accents)
- `↳` Arrow Down-Right (Index sub-items, tree menus)
- `▲` Triangle Up (Back to top / ascending status)
- `▼` Triangle Down (Collapsible indicators / descending status)
- `↗` / `↘` Diagonal Arrows (Outbound links / transition signs)

#### Star Set (Status & Accentuation)
- `✦` Black Four Pointed Star (Primary wayfinder accent, clean)
- `✧` White Four Pointed Star (Secondary wayfinder accent)
- `★` Black Star / `☆` White Star (Status / bookmarking)
- `✶` Six Pointed Star (Archival / catalog indicators)

#### Metro & Architectural Symbols (Structural Framing)
- `⊞` Squared Plus / `⊟` Squared Minus (Expand / collapse system structures)
- `⊠` Squared Times (Close, delete, absolute boundary)
- `⏀` / `⏁` / `⏂` Phase / Terminal Symbols (Terminal block endpoints, technical status)
- `⊚` Circle Bullseye / `⊛` Circle Star / `⊜` Circle Equal (System junction points, node states)
- `⏎` Return Key symbol (Actions, submission triggers)

#### Application Guidelines
- **Alignment:** Always align symbols using exact baseline adjustments (`vertical-align: middle` or `transform: translateY(...)`) so they feel part of the grid line.
- **Scale:** Decorative background symbols can be blown up to huge scales (e.g., `15vw`) at low opacity (e.g., `0.05`), acting as watermarks or grid intersections.

### Modernist Multi-Layering

True modernist design is flat, but "Wayfinder" and "Cargo" styles create depth through structural layering. Use the following techniques to construct dimensional compositions without resorting to drop shadows or realistic gradients:

1. **Overlaid Canvas Layouts:**
   - Stack full-screen or column-wide absolute containers on top of each other.
   - Example: A base layer containing a large background text grid, a middle layer containing desaturated imagery, and a top layer containing menus and layout rules.

2. **Contrast & Difference Layering:**
   - Use `mix-blend-mode: difference` or `mix-blend-mode: exclusion` on white text layers sitting on top of black/white images or overlapping shapes. The text will automatically invert color when crossing boundaries, creating high-contrast graphic tension.
   - Use `mix-blend-mode: multiply` on monochrome images inside colored backgrounds (e.g., black-and-white image in a yellow box) to merge the image dynamically into the color scheme.

3. **Text Border-Crossings:**
   - Anchor large display text directly onto structural border lines using negative margins or absolute offsets (e.g. `bottom: -0.5em`).
   - Split headings so that they cross between two colored sections, creating an asymmetric visual link.

---

## 10. CSS Framework / Design Tokens

A complete set of CSS custom properties defining the design system. Use these
as the single source of truth for any Swiss-Style web project.

```css
:root {
  /*
   * ─── Typography ──────────────────────────────────────────
   */

  /* Families */
  --font-sans: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --font-sans-alt: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  --font-classic: 'Akzidenz-Grotesk', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --font-wayfinder: 'Enreal', 'Jost Light', 'DM Sans Light', 'Outfit Light', ui-sans-serif, system-ui, sans-serif;

  /* Size scale — Perfect Fourth (1.25) */
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-md: 1.25rem;
  --text-lg: 1.563rem;
  --text-xl: 1.953rem;
  --text-2xl: 2.441rem;
  --text-3xl: 3.052rem;
  --text-4xl: 3.815rem;
  --text-5xl: 4.768rem;

  /* Weights */
  --weight-light: 300;
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-bold: 700;

  /* Line heights */
  --leading-tight: 1.0;
  --leading-heading: 1.1;
  --leading-body: 1.6;
  --leading-caption: 1.2;

  /* Tracking */
  --tracking-tight: -0.02em;
  --tracking-normal: 0;
  --tracking-wide: 0.042em;
  --tracking-upper: 0.05em;

  /*
   * ─── Spacing (8px base) ──────────────────────────────────
   */

  --space-0:  0px;
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  24px;
  --space-6:  32px;
  --space-8:  48px;
  --space-10: 64px;
  --space-12: 96px;
  --space-16: 128px;

  /*
   * ─── Colour ──────────────────────────────────────────────
   */

  --black:       #1A1A1A;
  --dark:        #2D2D2D;
  --mid-grey:    #6A6A6A;
  --cool-grey:   #A9B2B1;
  --light-grey:  #E5E5E5;
  --off-white:   #F4F3EE;
  --white:       #FFFFFF;
  --accent:      #D82C2C;
  --accent-blue: #2B5FD7;

  /* Semantic */
  --text-primary:   var(--black);
  --text-secondary: var(--mid-grey);
  --text-inverse:   var(--white);
  --bg-primary:     var(--white);
  --bg-secondary:   var(--off-white);
  --bg-inverse:     var(--black);
  --border:         var(--black);

  /*
   * ─── Grid ─────────────────────────────────────────────────
   */

  --grid-columns: 12;
  --grid-gap: 20px;
  --max-width: 1200px;
  --content-width: 960px;
  --measure: 66ch;

  /*
   * ─── Section ──────────────────────────────────────────────
   */

  --section-gap: clamp(4rem, 8vw, 8rem);
  --border-radius: 0px;
}
```

---

## 11. Spacing Scale

Every margin, padding, gap, and dimension must come from this scale. No
arbitrary values.

```
0    →   0px
1    →   4px    (fine)
2    →   8px    (baseline unit)
3    →   12px   (tight)
4    →   16px   (standard)
5    →   24px   (relaxed)
6    →   32px   (generous)
8    →   48px   (section padding)
10   →   64px   (wide)
12   →   96px   (spacious)
16   →   128px  (maximum)
```

### Application Examples

| Context | Token | Value |
|---------|-------|-------|
| Body padding (page edge) | `--space-6` | 32px |
| Gap between sections | `--space-8` or `--section-gap` | 48px – 8rem |
| Gap between grid items | `--grid-gap` | 20px |
| Padding inside a card | `--space-4` | 16px |
| Margin below a heading | `--space-3` | 12px |
| Margin below a paragraph | `--space-4` | 16px |
| Small element separation | `--space-2` | 8px |

---

## 12. Responsive Behaviour

Responsive design in Swiss Style is not about hamburger menus and stacked
columns. It is about preserving the composition across screen sizes.

### Breakpoints

```css
/* Tokens */
--bp-sm: 640px;
--bp-md: 768px;
--bp-lg: 1024px;
--bp-xl: 1280px;
```

### Collapse Strategy

| Screen | Grid Behaviour |
|--------|----------------|
| ≥ 1024px | 12-column grid, full compositional freedom |
| 768 – 1023px | 8-column grid, reduce gap to 16px, reduce padding to 24px |
| < 768px | Single column, 16px padding. One image per row. Type sizes reduce one step on the scale. |

### Mobile Non-Negotiables

- **No hamburger menu** unless the user has >6 nav items. Use a horizontal word
  list, or stack vertically.
- **Typography does not reflow wildly.** The same hierarchy applies. H1 is
  still bold, still the largest size on the page.
- **Images stay full-width** on mobile. No side-by-side images below 640px.
- **Whitespace shrinks but does not disappear.** Section gap at
  `clamp(2rem, 4vw, 4rem)` on small screens.

```css
@media (max-width: 767px) {
  .swiss-grid {
    grid-template-columns: 1fr;
    gap: 0;
    padding: 0 var(--space-4);
  }
}

@media (min-width: 768px) and (max-width: 1023px) {
  .swiss-grid {
    grid-template-columns: repeat(8, 1fr);
    gap: 16px;
    padding: 0 var(--space-5);
  }
}
```

---

## 13. Key Historical References

### Foundational Texts

| Work | Author | Relevance |
|------|--------|-----------|
| *Grid Systems in Graphic Design* (1961) | Josef Müller-Brockmann | The definitive book on grid methodology |
| *Typographie* (1967) | Emil Ruder | Typography as the foundation of communication |
| *Graphic Design Manual* (1965) | Armin Hofmann | Systematic approach to visual fundamentals |
| *Die neue Typographie* (1928) | Jan Tschichold | Early modernist typography manifesto |
| *Form + Communication* | Josef Müller-Brockmann | Swiss design philosophy extended |

### Key Designers

| Designer | Known For |
|----------|-----------|
| **Josef Müller-Brockmann** | Grid systems, Tonhalle concert posters, mathematical composition |
| **Emil Ruder** | Typography as primary tool, Basel School of Design |
| **Armin Hofmann** | Basel School, reductionist visual language, colour theory |
| **Max Bill** | Bauhaus connection, Art Concret, geometric abstraction |
| **Adrian Frutiger** | Univers, Frutiger, Avenir — rational typeface design |
| **Karl Gerstner** | Programmatic design, *Designing Programmes* |
| **Wim Crouwel** | Grid-obsessed, New Alphabet, Stedelijk Museum catalogues |
| **Wolfgang Weingart** | Pushed Swiss into postmodernism, "Swiss Punk" typography |
| **April Greiman** | Brought Swiss Style to US, blended with new wave |

### Iconic Works to Study

- Müller-Brockmann — Tonhalle Zürich concert posters (1950s–60s)
- Müller-Brockmann — *Der Film* poster
- Armin Hofmann — Basel Theatre posters
- Emil Ruder — *Typographie* spreads
- Max Bill — Ulm School of Design identity
- Wim Crouwel — Stedelijk Museum catalogues
- Josef Müller-Brockmann — *Automobil Club der Schweiz* posters
- Karl Gerstner — *Review* magazine spreads

---

## 14. Contemporary Reference Sites

### Cargo Sites (Study the layout, typography, and grid approach)

| Site | URL | Notes |
|------|-----|-------|
| Cargo Community | `cargo.site/community/in-use` | Browse the best current Cargo sites |
| Noble Design | `kendesign.cargo.site` | Portfolio with Swiss-leaning composition |
| Cargo Templates | `cargo.site/templates` | See the available starting points |

### Swiss-Style Web Design

| Site | URL | Notes |
|------|-----|-------|
| Swiss in CSS | `swissincss.com` | Historical Swiss posters recreated in CSS and animation |
| Swiss Themes | `swissthemes.design` | Modern Swiss design templates for Framer |
| Swiss UI Design Tokens | `github.com/swiss-ui/tokens` | Design tokens based on Swiss principles |

### Wayfinder & Contemporary Swiss

| Site | URL | Notes |
|------|-----|-------|
| Wayfinder Ventures | `wayfinder.com` | Dark-canvas, ultra-thin type, path illustration |
| HEX.inc Wayfinder case study | `hex.inc/work/wayfinder` | Full branding case study |
| HEX.inc | `hex.inc` | Studio behind Wayfinder — see their other work |

### Personal Reference Board

| Source | URL | Notes |
|--------|-----|-------|
| Pinterest Imagery Board | `br.pinterest.com/mytezy/imagery/` | ~500 pins — graphic design posters, brutalism, experimental typography, halftone/texture, retro sports graphics, archive aesthetics, event design, kinetic type. The user's personal visual vocabulary — the intersection of Swiss rigour with expressive/experimental elements. |

### Broader Inspirations

| Site | URL | Why |
|------|-----|-----|
| Apple | `apple.com` | Grid, photography, whitespace, typographic hierarchy |
| Medium | `medium.com` | Typographic reading experience, single-column Swiss |
| Stripe | `stripe.com` | Asymmetric layouts, grid discipline, limited palette |
| Pulumi brand | `brand.pulumi.com` | Inter typeface, typographic scale, Swiss-adjacent |

---

## 15. Design Review Checklist

Before considering any design complete, evaluate every point:

### Grid & Layout
- [ ] Is every element aligned to the grid?
- [ ] Are column spans varied across sections (no repeated equal columns)?
- [ ] Is the max-width constrained and centred?
- [ ] Are gutters consistent?
- [ ] Are any grid breaks deliberate rather than accidental?

### Typography
- [ ] Is only one typeface family used (plus mono where appropriate)?
- [ ] Are all font sizes from the modular scale?
- [ ] Is hierarchy carried by weight + size, not by colour or decoration?
- [ ] Is body text flush left, ragged right?
- [ ] Is the measure constrained to ~66ch on text-heavy sections?
- [ ] Are line heights generous (1.4–1.6 for body)?
- [ ] Is tracking intentional (tight for display, normal for body)?

### Whitespace
- [ ] Could any element be removed without losing communication?
- [ ] Is the section gap generous?
- [ ] Are margins and padding using the spacing scale?
- [ ] Is there at least one moment of deliberate emptiness?

### Colour
- [ ] Is the palette limited to neutrals + one accent?
- [ ] Is the accent used sparingly and meaningfully?
- [ ] Are there any drop shadows, gradients (unless Wayfinder), or rounded corners?

### Content
- [ ] Is photography the primary visual content?
- [ ] Are images full-bleed or aligned to the grid?
- [ ] Would the design work as well in black and white?

### Communication
- [ ] Does someone understand the message in under one second?
- [ ] Would removing the decorative elements change anything?
- [ ] Is the hierarchy clear without needing to interpret it?
- [ ] Does the design say the same thing to everyone?

### Wayfinder-Specific (if applicable)
- [ ] Is the canvas pure black?
- [ ] Is display type weight 300 with 0.042em tracking?
- [ ] Is the composition centred in the viewport?
- [ ] Are UI controls icon-only, monochrome, no labels?
- [ ] Does illustration occupy the full viewport?
- [ ] Is there a single, composed moment rather than a scroll of sections?

### Poster-to-Web / Graphic Design Transfer (if applicable)
- [ ] Does the composition translate to a screen with variable height?
- [ ] Is there a clear focal point (as a poster has)?
- [ ] Does type scale appropriately for the viewport (not fixed poster sizes)?
- [ ] Is the layout still legible when scrolled (not dependent on single-viewport visibility)?
- [ ] Are print conventions (bleed, trim marks, fold) used intentionally rather than accidentally?

### Brutalist (if applicable)
- [ ] Is the rawness intentional and purposeful, not just unfinished?
- [ ] Are system fonts used deliberately?
- [ ] Is there a clear hierarchy despite the anti-design?
- [ ] Does the aesthetic serve the message or just shock?

### Texture & Material (if applicable)
- [ ] Is every texture treatment serving a purpose (atmosphere, depth, focus)?
- [ ] Are textures performant (no massive PNGs, use SVG/CSS filters)?
- [ ] Do textures integrate with the typography rather than compete?

---

## 16. Poster-to-Web Translation

Swiss Style was born in print, and the posters of Müller-Brockmann, Hofmann,
and others remain the purest expression of its principles. Translating a
poster composition to the web requires adapting fixed-canvas thinking to a
variable-viewport medium.

### Key Differences

| Print Poster | Web Equivalent |
|-------------|----------------|
| Fixed dimensions (e.g. 90×128cm) | Variable viewport height, unknown device |
| Single, composed view | Scrollable, composable sections |
| One focal point | Multiple entry points across scroll |
| Exact colour control | Unknown display calibration |
| Physical texture (paper, ink) | CSS/SVG-simulated texture |

### Translation Patterns

**Pattern A: Full-Viewport Poster Hero**
The first viewport is a composed poster. Everything below is details.

```css
.poster-hero {
  height: 100vh;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  align-items: center;
  justify-items: start;
}
```

**Pattern B: Poster Strip**
A poster composition used as a full-width interruption within a scroll layout.

```css
.poster-strip {
  height: 80vh;
  min-height: 600px;
  position: relative;
  overflow: hidden;
}
```

**Pattern C: Fixed-Aspect Grid Cell**
Grid cells that maintain poster-like aspect ratios (4:3, 3:4, 2:3).

```css
.aspect-cell {
  aspect-ratio: 3 / 4;
  display: grid;
  place-items: center;
  overflow: hidden;
}
```

### Choosing What to Translate

When analysing a print poster for web translation, identify:

1. **Grid structure** — What modular grid underlies the poster? That becomes the
   CSS grid.
2. **Type hierarchy** — What is the primary/secondary/tertiary read? That maps
   to h1/h2/body in HTML.
3. **Focal point** — Where does the eye land first? That is the hero section.
4. **Whitespace** — Where is the breathing room? That becomes section gaps and
   padding.
5. **Texture** — Is there paper grain, halftone, or ink bleed? That becomes
   SVG/CSS filters.

---

## 17. Brutalist Web Design

Brutalism in web design is not about being unfinished — it is about being
**unpolished on purpose**. It rejects the slick, padded, rounded-corners
aesthetic of mainstream web design in favour of raw, honest, confrontational
communication. It shares Swiss Style's commitment to clarity and reduction,
but replaces mathematical neutrality with aggressive directness.

### Core Principles

| Principle | Meaning |
|-----------|---------|
| **Authenticity over elegance** | The design shows its bones. Raw HTML, unfiltered. |
| **Function over beauty** | If it works, it stays. Aesthetics are secondary. |
| **Confrontation** | The design should make you feel something — discomfort, surprise, urgency. |
| **Honesty of materials** | System fonts, default link colours, unstyled elements are features, not bugs. |
| **Maximalism within constraint** | Oversized type, harsh colours, intentionally broken grids. |

### Visual Vocabulary

| Element | Brutalist Approach |
|---------|-------------------|
| Typeface | System sans-serif (Arial/Helvetica) or monospace (Courier New/CONSOLA). No custom webfonts. |
| Type size | Often 2–3× larger than standard. H1 at 4–6rem. |
| Colour | High contrast. Default blue links (#0000EE), lime green on black, highlighter yellow. |
| Grid | 1-column or intentionally broken multi-column. Elements overlap. Margins are tight or zero. |
| Borders | Thick (`3px`–`5px`), black, solid. Underlines on everything. |
| Backgrounds | White, black, or aggressively coloured. No subtle greys. |
| Navigation | Visible list of links. Underlined. Blue. Like 1998. |
| Cursors | Use `cursor: pointer` or `cursor: crosshair` as a statement. |
| Interaction | Links change colour on hover. That's it. No animations, no micro-interactions. |

### When to Use Brutalist vs Swiss

| Context | Approach |
|---------|----------|
| Portfolio — minimal work | Swiss |
| Portfolio — loud, political, urgent work | Brutalist |
| Personal site / experimental | Brutalist |
| Corporate / brand site | Swiss |
| Art / gallery | Either |
| Blog — content-first | Swiss editorial |
| Blog — manifesto / polemic | Brutalist |
| Archive / directory | Brutalist |

### Code Pattern

```html
<!-- A brutalist page — minimal CSS, raw HTML, system defaults respected -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>brutal</title>
  <style>
    body {
      font-family: 'Courier New', Courier, monospace;
      font-size: 1rem;
      line-height: 1.5;
      max-width: 960px;
      margin: 2rem auto;
      padding: 1rem;
      background: #fff;
      color: #000;
    }
    h1 { font-size: 3.5rem; line-height: 1; margin-bottom: 0.5rem; }
    h2 { font-size: 2rem; }
    a { color: #0000EE; text-decoration: underline; }
    a:visited { color: #551A8B; }
    img { display: block; width: 100%; border: 3px solid #000; }
    hr { border: none; border-top: 4px solid #000; margin: 2rem 0; }
    ul { padding-left: 1.5rem; }
    .warning { background: #FF0; color: #000; padding: 1rem; font-weight: bold; }
  </style>
</head>
<body>
  <h1>This is a<br>brutalist page.</h1>
  <hr>
  <p>It looks like this because it has something to say.</p>
  <ul>
    <li><a href="/work">Work</a></li>
    <li><a href="/about">About</a></li>
    <li><a href="/contact">Contact</a></li>
  </ul>
  <hr>
  <img src="photo.jpg" alt="Work sample">
  <p class="warning">⚠ This site uses system fonts and default link colours.</p>
</body>
</html>
```

---

## 18. Texture & Material

Swiss design traditionally favours flat, untextured surfaces — but the
contemporary Swiss-adjacent vocabulary (including your Pinterest board) often
incorporates material texture: halftone dots, paper grain, ink bleed, noise,
and complex gradients.

### Texture Typeface

| Texture | Technique | Performance |
|---------|-----------|-------------|
| **Halftone** | SVG pattern or Canvas-generated dots | Medium |
| **Paper grain** | CSS `::after` with SVG noise filter | Good |
| **Photographic grain** | CSS `filter: contrast(1.2) brightness(0.9) saturate(0.3)` | Good |
| **Ink bleed / spread** | SVG filter `feGaussianBlur` + `feColorMatrix` | Medium |
| **Asynchronous gradient** | CSS `background` with multiple radial stops, `animation` | Good |
| **Noise texture** | CSS `::after` with tiny base64 noise PNG or SVG filter | Best |
| **Scan lines / CRT** | CSS `repeating-linear-gradient` overlay | Best |

### SVG Noise Filter (Paper Grain)

```css
.noise-overlay::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background: transparent;
  pointer-events: none;
  filter: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3C/svg%3E#n");
}
```

### Halftone Pattern (CSS)

```css
.halftone {
  background-image:
    radial-gradient(circle, #000 1px, transparent 1px);
  background-size: 4px 4px;
  background-color: #fff;
}
```

### Halftone (SVG Pattern)

```css
.halftone-svg {
  background-image: url("data:image/svg+xml,%3Csvg width='8' height='8' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='4' cy='4' r='1.5' fill='%23000'/%3E%3C/svg%3E");
}
```

### Asynchronous Gradient (Wayfinder-style)

```css
.gradient-mesh {
  background:
    radial-gradient(ellipse at 20% 50%, rgba(255,100,50,0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 20%, rgba(50,100,255,0.1) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 80%, rgba(255,50,150,0.08) 0%, transparent 50%);
}
```

### When to Add Texture

| Context | Texture Recommendation |
|---------|----------------------|
| Swiss portfolio (light) | None or very subtle paper grain |
| Swiss portfolio (dark) | Subtle noise |
| Editorial / magazine | Paper grain, ink bleed |
| Brutalist | Halftone, scan lines, CRT |
| Wayfinder-style | Asynchronous gradients, noise |
| Poster hero section | Halftone, grain |
| Archive / collection | Halftone, paper texture |

---

## 19. Editorial / Magazine Layout

Editorial design for the web adapts magazine spreads — multi-column text, pull
quotes, image hero spreads, captions, bylines — into responsive, scrollable
compositions.

### Spread Anatomy

A magazine spread on the web is a series of section grids, each with a
distinct layout:

```
Section 1: Hero Spread (full-bleed)
  [  image — 12 cols full-width  ]
  [  headline, byline — 6 cols, inset  ]

Section 2: Text Spread (two-column)
  [  body — 5 cols  |  body — 5 cols  |  gutter — 2  ]

Section 3: Image + Caption
  [  image — 8 cols  |  caption — 4 cols  ]

Section 4: Pull Quote Spread
  [  quote — 10 cols, centred  ]
  [  attribution — 4 cols, offset right  ]
```

### CSS Multi-Column for Editorial Text

```css
.editorial-text {
  column-count: 2;
  column-gap: var(--space-6, 32px);
  max-width: var(--measure, 66ch);
}

@media (max-width: 767px) {
  .editorial-text {
    column-count: 1;
  }
}
```

### Pull Quote

```css
.pull-quote {
  grid-column: 2 / 12;
  font-size: var(--text-2xl);
  font-weight: var(--weight-light);
  line-height: var(--leading-tight);
  letter-spacing: var(--tracking-tight);
  padding: var(--space-6) 0;
  border-top: 2px solid var(--black);
  border-bottom: 2px solid var(--black);
  margin: var(--space-8) 0;
}
```

### Drop Cap

```css
.drop-cap::first-letter {
  font-size: 4em;
  font-weight: var(--weight-bold);
  float: left;
  line-height: 0.8;
  margin-right: 0.15em;
  padding-top: 0.1em;
}
```

### Byline / Meta Block

```css
.byline {
  font-size: var(--text-sm);
  letter-spacing: var(--tracking-upper);
  text-transform: uppercase;
  color: var(--text-secondary);
}
```

### Editorial Type Scale

| Role | Size | Weight | Leading |
|------|------|--------|---------|
| Headline | 3xl–4xl | Bold (700) | 1.0 |
| Subhead | xl | Regular (400) | 1.1 |
| Body | base | Regular (400) | 1.6 |
| Caption | sm | Medium (500) | 1.2 |
| Pull quote | 2xl | Light (300) | 1.0 |
| Byline | xs | Medium (500) | 1.2 |

### Section Rhythms

Editorial pages follow a rhythm: open strong (hero), go deep (text/analysis),
punctuate (pull quote/image break), resolve (closing spread). Each section
type maps to a different grid pattern.

| Rhythm | Grid Pattern | Purpose |
|--------|-------------|---------|
| Hero | Full-bleed image + inset headline | Open the story |
| Text | 2-column or single narrow column | Depth / analysis |
| Break | Full-bleed image or pull quote | Pause / punctuate |
| Data | 3–4 columns of stats/charts | Evidence |
| Close | Full-bleed image or single strong statement | Resolve |

---

## 20. Image Analysis & Design Extraction

Photography is the primary visual material in Swiss Style. This section
describes how to read images as data — extracting dimensions, colour palettes,
texture complexity, and composition cues — and use that data to drive design
decisions.

### The Image Analysis Pipeline

When a project includes reference images, follow this pipeline before making
any layout or colour decision:

```
[ Reference images ] → [ Extract metadata ] → [ Generate palette ]
    → [ Recommend treatment ] → [ Assign grid placement ]
```

### Running the Analysis Tool

If `examples/analyze-images.js` exists in the project, run it to produce
structured data:

```bash
cd examples
node analyze-images.js                # outputs references.yaml
node analyze-images.js --format json  # outputs references.json
```

The output contains per-image metadata with these fields and design uses:

| Field | What it means | Design use |
|-------|---------------|------------|
| `width` / `height` | Pixel dimensions | Determines hero vs inset treatment. Full-width = 12-col hero. |
| `aspectRatio` | width/height | Guides grid column span. 16:9 = 12col. 4:3 = 8col. 1:1 = 6col. |
| `dominantColour` | Most frequent colour hex | Candidate for accent or background. |
| `palette` | Top 5 colours (hex) | Full palette extraction. Map to design tokens. |
| `entropy` | Texture complexity (0–8) | Low = flat/minimal (generous whitespace). High = busy (simple layout). |
| `sizeKB` | File size | Performance consideration. Large files may need compression. |
| `format` | Image format | WebP/AVIF preferred for performance. JPEG acceptable for photos. |

### Extracting a Colour Palette from Images

When no explicit palette is provided, extract one from the reference images:

1. **Collect dominant colours** from each image's `palette` field.
2. **Sort by frequency** — the most common neutral becomes `--off-white` or
   `--black`. The most saturated colour becomes `--accent`.
3. **Fill mid-tones** — intermediate colours map to `--mid-grey`,
   `--cool-grey`, `--text-secondary`.
4. **Output as CSS custom properties** with the standard token names.

Example mapping from image analysis:

```yaml
# references.yaml output
references:
  - file: hero-shot.jpg
    dominantColour: '#2A2A2A'    → --black
    palette:
      - '#2A2A2A'                → --black
      - '#F4F3EE'                → --off-white
      - '#D82C2C'                → --accent
      - '#6A6A6A'                → --mid-grey
      - '#A9B2B1'                → --cool-grey
```

### Tailoring Design to Image Content

Use image characteristics to drive design decisions:

| Image trait | Layout response | Typography response | Colour response |
|-------------|----------------|-------------------|-----------------|
| Low entropy, minimal | Generous whitespace, wide margins | Light weight (300), wide tracking | Off-white background, dark accent |
| High entropy, textured | Full-bleed, simple grid | Bold weight (700), tight tracking | Solid colour background, reduce noise |
| Dark tones | Light background or white text overlay | Thin weight on dark bg | High contrast accent |
| Light tones | Dark text, thin borders | Regular weight, standard leading | Strong accent for hierarchy |
| Portrait orientation | 6–8 col inset, vertical composition | Size 2xl headline, tight leading | Soft palette |
| Landscape / wide | Full-bleed hero, 12 col | Size 4xl display, wide tracking | Bold accent |

### Colour Palette Extraction Algorithm

When extracting a palette from images automatically:

1. **Quantise** the image to 16 colours using k-means or median cut (sharp
   does this internally via `stats()`).
2. **Select** the 5 most frequent colours.
3. **Classify** each as neutral (low saturation) or accent (high saturation).
4. **Rank** neutrals by luminance — darkest becomes `--black`, lightest
   becomes `--off-white`.
5. **Select** the most saturated colour as `--accent`.
6. **Discard** colours below 5% frequency to avoid noise.

### When Images Are Missing

If the project has no reference images, the agent should:

1. Ask the user for image descriptions or keywords.
2. Use placehold.co scaffolding images (e.g. `https://placehold.co/800x600`).
3. Propose a colour palette based on the brief's domain (Swiss, Wayfinder,
   brutalist, editorial) rather than extracted from images.
4. Note which design tokens are provisional and need real image data to
   finalise.

### Workflow for Designers

When a designer provides reference images:

1. **Analyse** — run the analysis tool to get structured data.
2. **Read** — study the extracted metadata with the image-editor agent.
3. **Extract** — pull palette candidates and composition cues.
4. **Map** — map extracted colours to design tokens.
5. **Design** — make grid, type, and colour decisions informed by the data.
6. **Validate** — delegate to design-critic to review the result.

---

## Usage Notes

When a user says "Swiss style", "cargo.site", "Wayfinder", "modernist", or
asks for a "graphic designer portfolio", invoke this skill's full context.

Output decisions as a designer would: reference grid columns, type scale
steps, and spacing units rather than breakpoints or component props. For
example, say *"this headline spans 8 columns at size 2xl"* not *"this h1 is
32px at desktop"*.

When writing CSS, always use the design tokens defined above. Never use
arbitrary values. Every margin, font-size, and colour should come from the
token system.

Prefer utility-first CSS (Tailwind-style) with the token set mapped to
utilities, or plain CSS with custom properties. Do not introduce a component
framework unless the user explicitly asks for one.
