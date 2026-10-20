// Source-only same-instance peer observation; no pipe or process is opened here.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eCreatorPeerBindingCandidate
{
    private const uint WaitTimeout = 0x00000102;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileTime
    {
        internal uint Low;
        internal uint High;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeClientProcessId(
        SafePipeHandle pipe, out uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetProcessId(SafeWaitHandle process);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetProcessTimes(
        SafeWaitHandle process, out FileTime creation, out FileTime exit,
        out FileTime kernel, out FileTime user);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(SafeWaitHandle process,
                                                    uint milliseconds);

    internal static string Screen(uint expectedPid, ulong expectedCreationTime,
                                  uint launchPid, ulong launchCreationTime,
                                  uint connectedClientPid, bool launchAlive)
    {
        if (expectedPid == 0 || expectedCreationTime == 0 ||
            launchPid == 0 || launchCreationTime == 0 ||
            connectedClientPid == 0)
            return "DENY:PEER_ID_UNAVAILABLE";
        if (!launchAlive) return "DENY:LAUNCH_EXITED_OR_UNKNOWN";
        if (launchPid != expectedPid ||
            launchCreationTime != expectedCreationTime ||
            connectedClientPid != launchPid)
            return "DENY:PEER_ID_MISMATCH";
        return "CANDIDATE:PEER_PROCESS_ONLY";
    }

    // Caller retains both exact handles and must observe token/image separately.
    internal static string Observe(SafePipeHandle connectedPipe,
                                   SafeWaitHandle launchedProcess,
                                   uint expectedPid,
                                   ulong expectedCreationTime)
    {
        if (connectedPipe == null || connectedPipe.IsInvalid ||
            connectedPipe.IsClosed || launchedProcess == null ||
            launchedProcess.IsInvalid || launchedProcess.IsClosed)
            return "DENY:INVALID_HANDLE";
        uint clientPid;
        if (!GetNamedPipeClientProcessId(connectedPipe, out clientPid))
            return "DENY:PIPE_CLIENT_ID_UNAVAILABLE";
        uint launchPid = GetProcessId(launchedProcess);
        FileTime created, exited, kernel, user;
        if (launchPid == 0 || !GetProcessTimes(launchedProcess, out created,
                                               out exited, out kernel, out user))
            return "DENY:LAUNCH_ID_UNAVAILABLE";
        ulong creationTime = ((ulong)created.High << 32) | created.Low;
        uint wait = WaitForSingleObject(launchedProcess, 0);
        return Screen(expectedPid, expectedCreationTime, launchPid,
                      creationTime, clientPid, wait == WaitTimeout);
    }
}
