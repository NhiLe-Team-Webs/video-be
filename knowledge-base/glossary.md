# Glossary

This document provides a comprehensive glossary of key terms and concepts used throughout the AI video automation project. Definitions are grounded in the reference transcripts, training documentation, and general machine learning terminology. Understanding these terms is essential for navigating the project's codebase and documentation effectively.

Short definitions grounded in the reference transcripts and training documentation.

- **Digital marketing** - marketing activities executed through digital channels (SEO, social media, PPC, email, websites). *Related:* Traditional marketing.
- **Traditional marketing** - offline channels such as print, radio, direct mail; contrasted with digital to highlight reach and measurability differences. *See also:* [planning_guidelines.md](planning_guidelines.md#narrative-alignment).
- **SEO (Search Engine Optimization)** - practice of improving organic visibility; central focus of the speaker's career pivot in Video 1. *Related:* Search marketing.
- **B-roll** - supplemental footage used to visualise or emphasise narration. *See also:* [asset_catalogs.md](asset_catalogs.md#catalog-overview).
- **Callout / Highlight** - on-screen emphasis for key phrases, statistics, or warnings, typically rendered as `text_overlay`.
- **Framework** - structured list or set of stages (for example, three-part learning model, four practice principles); often represented with progressive overlays.
- **Stage 1 / 2 / 3 (Learning)** - understand fundamentals -> connect fundamentals -> practise execution (Video 1).
- **Product marketing** - showcasing features and tangible benefits of a physical good.
- **Service marketing** - selling the outcome or end state (experience, trust, transformation) rather than the service mechanics.
- **B2B (Business to Business)** - companies selling to other businesses; longer cycles, committee decisions.
- **B2C (Business to Consumer)** - companies selling directly to consumers; faster decisions, emotion-driven.
- **Feature vs Benefit** - feature describes what something is; benefit explains the value it delivers (Video 2 pen example).
- **Trust signals** - elements that reinforce credibility (awards, experience, social proof).
- **Motion cue** - visual effect (zoom, slide) signalling a narrative shift or emphasis. *See also:* Motion rules in `motion_rules.json`.
- **Embedding** - numeric vector representing semantic meaning of text or assets, used for similarity search and modelling (for example, Sentence-BERT). *Related:* Feature engineering.
- **Word2Vec / GloVe / Sentence-BERT** - families of embedding models; Sentence-BERT produces sentence-level vectors well suited for transcript windows.
- **One-hot encoding** - representation where each category maps to a unique vector with a single 1 and the rest 0; used for element types and styles.
- **Regression head** - model component predicting continuous values (for example, `timestamp`, `duration`). *See:* `training_pipeline.md`.
- **Multi-label classification** - predicting multiple boolean outcomes simultaneously (for example, presence of several element families in a window).
- **MAE (Mean Absolute Error)** - evaluation metric for regression measuring average absolute difference between predicted and true values.
- **F1 score** - harmonic mean of precision and recall; used to assess classification performance.
- **BLEU / ROUGE** - text generation metrics comparing model output to reference wording; apply to overlay copy evaluation.
- **Early stopping** - training technique that halts optimisation when validation performance stops improving to avoid overfitting.
- **Curriculum learning** - training strategy that teaches simpler tasks before harder ones (for example, predict type before content).
- **Confidence score** - probability estimate output by the model indicating reliability of a prediction; captured in `element_schema.json`.
- **Layer stack** - render order from `main` -> `video` -> `overlay` -> `audio` -> `transition`; detailed in [element_definitions.md](element_definitions.md#layer-stack).
- **Context tag** - short descriptive string indicating narrative intent (for example, "mistake warning"); used to query asset catalogs and maintain coherence.
