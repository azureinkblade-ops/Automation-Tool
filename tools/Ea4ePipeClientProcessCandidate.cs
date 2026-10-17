// Read-only pipe/process object match; the caller must own the expected handle.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientProcessCandidate
{
    private const uint WaitTimeout = 0x00000102;

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeClientProcessId(
        SafePipeHandle pipe, out uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetProcessId(IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

    internal static string Denial(SafePipeHandle pipe, IntPtr expectedProcess)
    {
        if (pipe == null || pipe.IsInvalid || pipe.IsClosed)
            return "PIPE_HANDLE_UNAVAILABLE";
        if (expectedProcess == IntPtr.Zero || expectedProcess == new IntPtr(-1)
            || expectedProcess == new IntPtr(-2))
            return "EXPECTED_PROCESS_HANDLE_INVALID";
        uint expectedId = GetProcessId(expectedProcess);
        if (expectedId == 0 || WaitForSingleObject(expectedProcess, 0) != WaitTimeout)
            return "EXPECTED_PROCESS_NOT_LIVE";
        uint clientId;
        if (!GetNamedPipeClientProcessId(pipe, out clientId) || clientId == 0)
            return "CLIENT_PROCESS_UNAVAILABLE";
        return clientId == expectedId ? null : "CLIENT_PROCESS_MISMATCH";
    }
}
