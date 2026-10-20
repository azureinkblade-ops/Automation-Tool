// Declaration-only candidate; no caller or native creation route is wired.
using System;
using System.Runtime.InteropServices;

internal static class Ea4eDirectory2NativeAbiCandidate
{
    [DllImport("kernel32.dll", EntryPoint = "CreateDirectory2W",
        CharSet = CharSet.Unicode, ExactSpelling = true,
        CallingConvention = CallingConvention.Winapi, SetLastError = true)]
    private static extern IntPtr CreateDirectory2W(
        string path, uint desiredAccess, uint shareMode,
        uint directoryFlags, IntPtr securityAttributes);
}
