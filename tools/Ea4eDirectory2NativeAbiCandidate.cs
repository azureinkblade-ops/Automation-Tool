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

    // Unwired call primitive. A reviewed one-attempt owner must screen its result.
    internal static IntPtr InvokeUnwired(
        string path, uint desiredAccess, uint shareMode,
        uint directoryFlags, IntPtr securityAttributes, out int lastError)
    {
        IntPtr returned = CreateDirectory2W(path, desiredAccess, shareMode,
            directoryFlags, securityAttributes);
        lastError = Marshal.GetLastWin32Error();
        return returned;
    }
}
