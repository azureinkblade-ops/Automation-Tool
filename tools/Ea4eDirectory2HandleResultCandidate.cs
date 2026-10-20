// Value-only result screen; never invokes a native directory API.
using System;

internal static class Ea4eDirectory2HandleResultCandidate
{
    internal static string Screen(IntPtr returned)
    {
        if (returned == IntPtr.Zero) return "DENY:NULL_HANDLE";
        if (returned == new IntPtr(-1)) return "DENY:INVALID_HANDLE_VALUE";
        return "CANDIDATE:NON_SENTINEL_ONLY";
    }
}
