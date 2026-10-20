// Export-presence observation only; never invokes CreateDirectory2W.
using System;
using System.Runtime.InteropServices;

internal static class Ea4eDirectory2AvailabilityCandidate
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true,
        EntryPoint = "GetModuleHandleW", SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string module);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, ExactSpelling = true,
        EntryPoint = "GetProcAddress", SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);

    internal static string Observe()
    {
        IntPtr module = GetModuleHandle("kernel32.dll");
        if (module == IntPtr.Zero) return "DENY:KERNEL32_UNAVAILABLE";
        if (GetProcAddress(module, "CreateDirectory2W") == IntPtr.Zero)
            return "DENY:CREATE_DIRECTORY_2_UNAVAILABLE";
        return "CANDIDATE:EXPORT_PRESENT_ONLY";
    }
}
