// Source-only probe candidate. Native mode needs a separate one-shot authorization.
using System;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4e92qpVolumeReadbackProbe
{
    private const uint FileReadAttributes = 0x80;
    private const uint FileShareAll = 0x07;
    private const uint OpenExisting = 3;
    private const uint BackupSemantics = 0x02000000;
    private const uint OpenReparsePoint = 0x00200000;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode,
        ExactSpelling = true, EntryPoint = "CreateFileW", SetLastError = true)]
    private static extern SafeFileHandle OpenDirectory(string path,
        uint access, uint share, IntPtr securityAttributes,
        uint disposition, uint flags, IntPtr template);

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--describe")
        {
            Console.WriteLine("SOURCE_ONLY:PROGRAMDATA_VOLUME_FLAG_PROBE");
            return 0;
        }
        if (args.Length != 5 || args[0] != "--native-volume")
            return 2;

        Guid ceremony;
        DateTime deadline;
        if (String.IsNullOrEmpty(args[1]) || String.IsNullOrEmpty(args[2]) ||
            !Guid.TryParseExact(args[3], "D", out ceremony) ||
            ceremony == Guid.Empty ||
            !DateTime.TryParseExact(args[4], "yyyy-MM-ddTHH:mm:ssZ",
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal |
                DateTimeStyles.AdjustToUniversal, out deadline))
            return Deny("INPUT", 10);
        TimeSpan remaining = deadline - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero || remaining > TimeSpan.FromMinutes(2))
            return Deny("DEADLINE", 11);

        try
        {
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
            {
                if (identity.User == null ||
                    !String.Equals(identity.User.Value, args[2],
                        StringComparison.Ordinal))
                    return Deny("OPERATOR", 12);
            }
            string root;
            if (Ea4eProgramDataKnownFolderCandidate.Resolve(out root) != null ||
                !String.Equals(root, args[1],
                    StringComparison.OrdinalIgnoreCase))
                return Deny("KNOWN_FOLDER", 13);

            using (SafeFileHandle retained = OpenDirectory(root,
                FileReadAttributes, FileShareAll, IntPtr.Zero, OpenExisting,
                BackupSemantics | OpenReparsePoint, IntPtr.Zero))
            {
                if (retained == null || retained.IsInvalid)
                    return Deny("PARENT_OPEN", 14);
                uint flags;
                int lastError;
                string result = Ea4eDirectoryVolumeAclCandidate.Read(
                    retained, out flags, out lastError);
                if (result != "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY")
                    return Deny("VOLUME_FLAG", 15);
                Console.WriteLine("OBSERVED:PERSISTENT_ACLS_FLAG_ONLY");
                return 0;
            }
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return Deny("PROBE_EXCEPTION", 16);
        }
    }

    private static int Deny(string reason, int code)
    {
        Console.WriteLine("DENY:" + reason);
        return code;
    }
}
