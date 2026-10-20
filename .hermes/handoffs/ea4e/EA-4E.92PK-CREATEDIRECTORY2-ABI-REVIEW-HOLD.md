# EA-4E.92PK CreateDirectory2 ABI Review Hold

Source-only review of the proposed native first-child adapter found an
unresolved Microsoft documentation discrepancy. The W and A pages each show
a five-argument HANDLE declaration, but their examples pass six arguments.
The W page says failure returns zero; the A page says failure returns
INVALID_HANDLE_VALUE. The public header declaration can establish the
parameter list but not which failure sentinel the host implementation uses.

- W: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w
- A: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2a
- Pinned public SDK header: https://github.com/microsoft/win32metadata/blob/76c04c2021ef4a831a6f1e06d9566002d746139b/generation/WinSDK/RecompiledIdlHeaders/um/fileapi.h

The local Windows SDK include tree was not present. Export presence from
92PF does not settle the ABI or failure result. In particular, checking only
for zero could treat INVALID_HANDLE_VALUE as a valid retained handle. Do not
wire or execute the native adapter on that basis. A future adapter must
reject both zero and INVALID_HANDLE_VALUE, capture GetLastError immediately,
and still receive an independent source/ABI review and a new bounded native
authorization before any mutating qualification. Treat collision, uncertain
result, or absent returned handle as HOLD without adoption, retry, or cleanup
by path. The 92PJ fake-port test does not close this native gate.

No directory, ACL, Docker, receiver/model, GPU, ComfyUI, or production state
was changed in this review. Full 92NK, the strict 92AT exact mapped-byte
invariant, and production remain HOLD/REJECT as previously recorded.
