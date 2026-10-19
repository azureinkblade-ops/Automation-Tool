// Read-only kernel process observation from one connected pipe; no authority.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientProcessLeaseCandidate
{
    private const uint ProcessQueryLimitedInformation = 0x1000;
    private const uint Synchronize = 0x00100000;
    private const uint WaitTimeout = 0x00000102;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileTime
    {
        internal uint Low;
        internal uint High;

        internal long Value
        {
            get { return ((long)High << 32) | Low; }
        }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeClientProcessId(
        SafePipeHandle pipe, out uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern SafeWaitHandle OpenProcess(
        uint desiredAccess, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle,
        uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetProcessId(SafeWaitHandle process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(
        SafeWaitHandle process, uint milliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetProcessTimes(
        SafeWaitHandle process, out FileTime creation, out FileTime exit,
        out FileTime kernel, out FileTime user);

    internal static string Denial(
        SafePipeHandle pipe, Func<IntPtr, uint, long, string> observe)
    {
        if (pipe == null || pipe.IsInvalid || pipe.IsClosed)
            return "PIPE_HANDLE_UNAVAILABLE";
        if (observe == null) return "PROCESS_OBSERVER_UNAVAILABLE";
        uint clientId;
        if (!GetNamedPipeClientProcessId(pipe, out clientId) || clientId == 0)
            return "CLIENT_PROCESS_UNAVAILABLE";
        using (SafeWaitHandle process = OpenProcess(
            ProcessQueryLimitedInformation | Synchronize, false, clientId))
        {
            if (process == null || process.IsInvalid || process.IsClosed)
                return "CLIENT_PROCESS_OPEN_DENIED";
            if (GetProcessId(process) != clientId
                || WaitForSingleObject(process, 0) != WaitTimeout)
                return "CLIENT_PROCESS_NOT_LIVE";
            FileTime creation;
            FileTime exit;
            FileTime kernel;
            FileTime user;
            if (!GetProcessTimes(process, out creation, out exit,
                                 out kernel, out user)
                || creation.Value <= 0)
                return "CLIENT_CREATION_TIME_UNAVAILABLE";
            uint beforeCallback;
            if (!GetNamedPipeClientProcessId(pipe, out beforeCallback)
                || beforeCallback != clientId)
                return "CLIENT_PROCESS_CHANGED";

            string denial;
            try
            {
                denial = observe(process.DangerousGetHandle(), clientId,
                                 creation.Value);
            }
            catch { return "PROCESS_OBSERVATION_FAILED"; }
            if (denial != null) return denial;

            uint afterCallback;
            if (!GetNamedPipeClientProcessId(pipe, out afterCallback)
                || afterCallback != clientId
                || GetProcessId(process) != clientId
                || WaitForSingleObject(process, 0) != WaitTimeout)
                return "CLIENT_PROCESS_CHANGED";
            return null;
        }
    }
}
