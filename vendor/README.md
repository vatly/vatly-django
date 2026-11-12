# Unpublished dependency bootstrap

These unmodified 0.1.0a2 wheels are built from reviewed SDK and Fluent sources:
SDK commit `5ba13e57ff99554497d2dd796641ba44c28c8d37` and Fluent commit
`94815a1ce4bde2c3938361ce29ea215d62cdaba4`.
They allow private-repo CI and fresh orbs
to work before PyPI publication, without GitHub credentials for sibling repos.
uv's local sources affect development only. Published wheel metadata uses the exact
normal PyPI requirements. Vendor files are not included in the package wheel.
Publish SDK → Fluent → Django, only after explicit authorization. See SHA256SUMS.
