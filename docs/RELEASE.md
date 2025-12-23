# Release Guide

## How to Create a New Release

This project uses GitHub Actions to automatically build and publish releases to PyPI when you create a new version tag.

### Prerequisites

- `PYPI_API_TOKEN` secret configured in GitHub repository settings
- Maintainer access to the repository

### Release Process

1. **Update Version Number**

   Edit `pyproject.toml` and update the version:
   ```toml
   [project]
   name = "email-archiver"
   version = "0.2.0"  # Update this
   ```

2. **Commit Version Change**

   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin main
   ```

3. **Create and Push Tag**

   ```bash
   # Create annotated tag
   git tag -a v0.2.0 -m "Release version 0.2.0"
   
   # Push tag to GitHub
   git push origin v0.2.0
   ```

4. **Automated Process**

   Once the tag is pushed, GitHub Actions will automatically:
   - Create a GitHub Release with auto-generated release notes
   - Build the Python package using UV
   - Publish to PyPI using the `PYPI_API_TOKEN` secret

5. **Verify Release**

   - Check GitHub Releases: https://github.com/therealtimex/email-archiver/releases
   - Check PyPI: https://pypi.org/project/email-archiver/
   - Test installation: `pip install email-archiver`

### Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version (1.0.0): Incompatible API changes
- **MINOR** version (0.2.0): New functionality, backwards compatible
- **PATCH** version (0.1.1): Bug fixes, backwards compatible

### Example: First Release

```bash
# Ensure version is set correctly
cat pyproject.toml | grep version

# Create and push tag
git tag -a v0.1.0 -m "Initial release"
git push origin v0.1.0

# Wait for GitHub Actions to complete
# Check: https://github.com/therealtimex/email-archiver/actions
```

### Troubleshooting

**Release failed to publish to PyPI:**
- Check GitHub Actions logs
- Verify `PYPI_API_TOKEN` is correctly set
- Ensure version number doesn't already exist on PyPI

**Tag already exists:**
```bash
# Delete local tag
git tag -d v0.1.0

# Delete remote tag
git push origin :refs/tags/v0.1.0

# Create new tag
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

## Manual Release (if needed)

If you need to publish manually:

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Build package
uv build

# Install twine
pip install twine

# Upload to PyPI
twine upload dist/*
```

## Pre-release Testing

Before creating a release tag, test the build locally:

```bash
# Build package
uv build

# Check dist/ directory
ls -lh dist/

# Install locally
pip install dist/email_archiver-*.whl

# Test installation
eesa --help
```
