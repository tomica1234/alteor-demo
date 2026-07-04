---
name: image-lp-from-reference
description: Use this skill when the user provides one or more reference images, screenshots, Figma exports, generated mockups, or design comps and asks to implement them as a landing page. Do not use this skill to generate images. The user supplies the images.
---

# Image LP from Reference

You are implementing a landing page from user-supplied reference image(s). The images are the source of truth.

## Non-negotiable workflow

1. **Do not generate images.** The user supplies the design images.
2. **Do not start coding before analysis.** First inspect every supplied image.
3. **Map images to sections.** Decide whether each image represents a full page, a hero, a feature section, a CTA, a pricing block, FAQ, or another section.
4. **Write a visual analysis before editing code.** Include:
   - layout structure
   - section order
   - typography hierarchy
   - color palette
   - spacing scale
   - buttons and CTA hierarchy
   - card/grid structure
   - decorative elements
   - responsive/mobile implications
   - assets that must be recreated with CSS/SVG/HTML rather than copied
5. **Then implement.** Match the images as closely as possible, but use real semantic HTML and maintainable CSS.
6. **Run the project checks.** At minimum run the build command. Fix errors before finishing.

## Implementation rules

- Build a real LP, not a static screenshot pasted into the page.
- Recreate the visual language with components, layout, CSS, SVG, gradients, borders, shadows, typography, and spacing.
- Avoid generic SaaS templates if the reference image has a distinct direction.
- Use Japanese copy when the product/user brief is Japanese.
- Do not use lorem ipsum.
- If text in the image is unreadable, infer reasonable Japanese LP copy from the user's brief and mark the assumption briefly.
- Keep the page responsive for desktop, tablet, and mobile.
- Use accessible semantic structure: header, main, section, nav, footer, h1-h3 hierarchy.
- Use buttons and links with clear labels.
- Do not introduce heavy dependencies unless the project already uses them.
- Prefer existing stack conventions. If the project is Vite/React, use React + CSS/CSS modules. If it is Next.js, use Next conventions.

## Visual fidelity checklist

Before final response, verify:

- Hero composition matches the supplied image direction.
- Section rhythm and whitespace feel close to the reference.
- Color palette is consistent.
- Button styles and CTA hierarchy are consistent.
- Cards/tables/pricing blocks match the visual intent.
- Mobile layout is not broken.
- Build passes.

## For B2B secure local AI LPs

When the brief is about secure/local AI agents, the copy should emphasize:

- 機密情報を外部AIに送らないこと
- 社内ナレッジ活用
- 士業・法務・知財・人事・経営企画など機密性の高い業務
- オンプレミスまたは閉域/専用環境
- 導入支援・権限設計・監査ログ・社内文書検索
- 安全チャット、ナレッジ検索、文書作成、業務エージェント化

Security should be treated as a primary value proposition, not a small footer note.
