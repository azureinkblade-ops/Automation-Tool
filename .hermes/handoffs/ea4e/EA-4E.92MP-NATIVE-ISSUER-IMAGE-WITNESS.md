# EA-4E.92MP native issuer image witness

Status: NON-LIVE CANDIDATE / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `dfee4cef4b933f9831659be6e254dbeeca899bda`.

`tools/Ea4eProtectedIssuerImage.cs` reads the current process executable
path and hashes that file's bytes with SHA-256. It compares the observed
path and digest with explicit expected values. Invalid paths or hashes,
foreign paths, and changed file bytes deny. The expected path and digest
must eventually come from an independently reviewed protected policy, not
from the app request. The pure comparison probe is test-only; no grant
issue, store write, Docker mutation, UAC, receiver, or model call exists.

Focused current-image and negative tests: 8 passed. Adjacent native token,
complete network-grant candidate, and v4 grant-store tests: 56 passed.
The system-temp-dependent fixture ran with a fresh writable repository
output directory set as `TEMP`/`TMP` and pytest base for that command.

This measures the executable file at an observed path. It does not attest
the running image section's exact mapped bytes, prove the file was protected
against replacement before opening, inspect ancestor reparse points or
effective ACLs, or bind a trusted installation. It therefore does not close
strict 92AT, qualify a protected issuer, or authorize a live action. Those
remaining checks need their own reviewed implementation and qualification.
