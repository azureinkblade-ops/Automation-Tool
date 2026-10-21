// Unwired directory handle owner. A failed release is observable, not retried.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal sealed class Ea4eDirectoryObservedHandleCandidate
    : SafeHandleZeroOrMinusOneIsInvalid
{
    private bool releaseAttempted;
    private bool releaseSucceeded;
    private int releaseError;

    [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    internal Ea4eDirectoryObservedHandleCandidate(IntPtr raw) : base(true)
    {
        if (raw == IntPtr.Zero || raw == new IntPtr(-1))
            throw new ArgumentException("Invalid directory handle", "raw");
        SetHandle(raw);
    }

    internal bool ReleaseObserved { get { return releaseAttempted && releaseSucceeded; } }
    internal int ReleaseError { get { return releaseError; } }

    protected override bool ReleaseHandle()
    {
        bool released = CloseHandle(handle);
        int error = released ? 0 : Marshal.GetLastWin32Error();
        releaseError = error;
        releaseSucceeded = released;
        releaseAttempted = true;
        return released;
    }
}
