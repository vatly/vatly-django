# Unpublished dependency bootstrap

These unmodified wheels are built from vatly/vatly-api-python main `4be4eaf` and
vatly/vatly-fluent-python main `b297d85`. They allow private-repo CI and fresh orbs
to work before PyPI publication, without GitHub credentials for sibling repos.
uv's local sources affect development only. Published wheel metadata uses the exact
normal PyPI requirements. Vendor files are not included in the package wheel.
Publish SDK → Fluent → Django, only after explicit authorization. See SHA256SUMS.
