# Unpublished dependency bootstrap

These unmodified 0.1.0a2 wheels are built from reviewed SDK and Fluent sources:
`vatly-api-python` at commit `26adc74d8553238bcc94da2f650619de93e9cbd6` and
`vatly-fluent-python` at commit `ca8f394821fc1d64002f5f69596a81e91e51d9c9`.
They allow private-repo CI and fresh orbs
to work before PyPI publication, without GitHub credentials for sibling repos.
uv's local sources affect development only. Published wheel metadata uses the exact
normal PyPI requirements. Vendor files are not included in the package wheel.
Publish SDK → Fluent → Django, only after explicit authorization. See SHA256SUMS.
