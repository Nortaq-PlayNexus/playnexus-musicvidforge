# Contributing to MusicVidForge

Thanks for wanting to help! MusicVidForge is a small, focused project and every
contribution counts.

## How to contribute

1. **Fork** the repository and create a feature branch:

   ```bash
   git checkout -b feat/my-improvement
   ```

2. **Make your change.** Follow the existing code style — keep functions small,
   no new dependencies unless they add real value, and no comments that just
   restate the code.
3. **Add or update tests** in `tests/` for any behaviour you change.
4. **Run the test suite** locally:

   ```bash
   pip install -r requirements.txt pytest
   pytest
   ```

5. **Commit** with a clear, conventional message:

   ```text
   feat: add new template
   fix: correct beat offset on long tracks
   docs: expand architecture notes
   ```

6. **Open a pull request** against `main` and describe what and why.

## Good first ideas

See the [Roadmap](docs/ROADMAP.md) for planned features. Small, safe improvements:

- New beat-synced templates.
- GPU-accelerated preview thumbnails.
- Localisation of the UI.
- More output presets.

## Code of conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md). Be respectful —
this is a friendly little project.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
