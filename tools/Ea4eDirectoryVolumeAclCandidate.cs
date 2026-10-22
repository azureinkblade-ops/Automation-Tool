// Unwired retained-handle volume capability candidate; not issuer admission.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eDirectoryVolumeAclCandidate
{
    internal const uint FilePersistentAcls = 0x00000008;
    internal delegate bool VolumeInformationReader(SafeFileHandle file,
        out uint flags, out int lastError);

    [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetVolumeInformationByHandleW(
        SafeFileHandle file, IntPtr volumeName, uint volumeNameSize,
        IntPtr volumeSerial, IntPtr maximumComponentLength,
        out uint fileSystemFlags, IntPtr fileSystemName,
        uint fileSystemNameSize);

    internal static string Classify(bool callSucceeded, uint fileSystemFlags)
    {
        if (!callSucceeded) return "DENY:VOLUME_INFORMATION_UNAVAILABLE";
        return (fileSystemFlags & FilePersistentAcls) != 0
            ? "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY"
            : "DENY:VOLUME_ACLS_UNSUPPORTED";
    }

    private static bool ReadNative(SafeFileHandle retained, out uint flags,
                                   out int lastError)
    {
        flags = 0;
        bool succeeded = GetVolumeInformationByHandleW(retained,
            IntPtr.Zero, 0, IntPtr.Zero, IntPtr.Zero, out flags,
            IntPtr.Zero, 0);
        lastError = succeeded ? 0 : Marshal.GetLastWin32Error();
        return succeeded;
    }

    // The injected reader permits inert failure tests; its result is not issuer authority.
    internal static string ReadWith(SafeFileHandle retained,
        VolumeInformationReader reader, out uint flags, out int lastError)
    {
        flags = 0;
        lastError = 0;
        if (reader == null) return "DENY:VOLUME_READER_MISSING";
        try
        {
            if (retained == null || retained.IsInvalid || retained.IsClosed)
                return "DENY:RETAINED_HANDLE_UNAVAILABLE";
            uint observedFlags;
            int observedError;
            bool succeeded = reader(retained, out observedFlags, out observedError);
            lastError = succeeded ? 0 : observedError;
            string result = Classify(succeeded, observedFlags);
            if (result == "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY")
                flags = observedFlags;
            return result;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            flags = 0;
            lastError = 0;
            return "DENY:VOLUME_INFORMATION_UNAVAILABLE";
        }
    }

    // Caller retains this exact handle and must independently bind its parent.
    internal static string Read(SafeFileHandle retained, out uint flags,
                                out int lastError)
    {
        return ReadWith(retained, ReadNative, out flags, out lastError);
    }
}
