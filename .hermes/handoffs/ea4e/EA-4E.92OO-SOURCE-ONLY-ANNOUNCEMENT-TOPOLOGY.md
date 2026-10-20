# EA-4E.92OO source-only announcement topology entry

Status: NON-LIVE SOURCE-ONLY / NO INSTALLED NAMESPACE OBSERVED.
Governing parent: `64332bf97857e60a42185b6dc31ca5abc694d109`.

The existing protected path-topology helper now has one separate
`DenialWithAnnouncementLeaf` entry point. It keeps the previous callers'
share modes unchanged. Only the new announcement leaf uses 92OM's
`FILE_SHARE_READ | FILE_SHARE_WRITE` mask so a future reader can coexist
with the retained creator writer. Every path-component handle remains open
through the observer callback. The new entry point denies a missing observer
before any native open, and the fixture has no native-open CLI.

This is a routing and topology candidate, not a trusted file/issuer witness.
The observer must still check the exact installed root, owner/DACL/label,
file identity, creator process, 92ON bounded bytes, 92OJ canonical record,
and durable one-use accounting. A callback returning success without those
checks would not qualify the announcement. The legacy helper's own topology
test remains an inert workspace-file test, not an installed-namespace probe.

Focused new/legacy topology and access tests passed 26; three symlink cases
were skipped because the environment could not create them. No production,
Kilo/OpenCode receiver, model, Docker mutation, GPU, or ComfyUI action was
performed. Full 92NK and native installation remain HOLD.
