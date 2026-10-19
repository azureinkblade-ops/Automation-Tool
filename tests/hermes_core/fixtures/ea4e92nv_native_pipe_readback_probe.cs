// Source-only fixture. The native mode requires a separately bounded ceremony.
using System;
using System.Globalization;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4e92nvNativePipeReadbackProbe
{
    private sealed class PrivilegeRestoreFailure : Exception { }

    private const uint TokenAdjustPrivileges = 0x20;
    private const uint TokenQuery = 0x08;
    private const uint SePrivilegeEnabled = 0x02;

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid
    {
        internal uint Low;
        internal int High;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenPrivilege
    {
        internal Luid Id;
        internal uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenPrivileges
    {
        internal uint Count;
        internal TokenPrivilege Privilege;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(IntPtr process, uint access,
        out SafeWaitHandle token);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LookupPrivilegeValue(string system,
        string name, out Luid value);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AdjustTokenPrivileges(SafeWaitHandle token,
        [MarshalAs(UnmanagedType.Bool)] bool disableAll,
        ref TokenPrivileges requested, uint previousLength,
        out TokenPrivileges previous, out uint returnedLength);

    private sealed class SecurityPrivilegeScope : IDisposable
    {
        private readonly SafeWaitHandle token;
        private readonly TokenPrivileges previous;
        private readonly bool changed;

        private SecurityPrivilegeScope(SafeWaitHandle token,
                                       TokenPrivileges previous)
        {
            this.token = token;
            this.previous = previous;
            changed = previous.Count == 1;
        }

        internal static SecurityPrivilegeScope Enable()
        {
            SafeWaitHandle token;
            if (!OpenProcessToken(GetCurrentProcess(),
                TokenAdjustPrivileges | TokenQuery, out token))
                throw new InvalidOperationException("Token open denied");
            TokenPrivileges previous = new TokenPrivileges();
            bool adjusted = false;
            try
            {
                Luid id;
                if (!LookupPrivilegeValue(null, "SeSecurityPrivilege", out id))
                    throw new InvalidOperationException("Privilege unavailable");
                var requested = new TokenPrivileges {
                    Count = 1,
                    Privilege = new TokenPrivilege {
                        Id = id, Attributes = SePrivilegeEnabled,
                    },
                };
                uint returned;
                bool success = AdjustTokenPrivileges(token, false, ref requested,
                    (uint)Marshal.SizeOf(typeof(TokenPrivileges)),
                    out previous, out returned);
                int error = Marshal.GetLastWin32Error();
                adjusted = success && error == 0;
                if (!adjusted || previous.Count > 1 ||
                    returned > Marshal.SizeOf(typeof(TokenPrivileges)) ||
                    (previous.Count == 1 &&
                     (previous.Privilege.Id.Low != id.Low ||
                      previous.Privilege.Id.High != id.High)))
                    throw new InvalidOperationException("Privilege enable denied");
                return new SecurityPrivilegeScope(token, previous);
            }
            catch
            {
                if (adjusted && previous.Count == 1)
                {
                    TokenPrivileges ignored;
                    uint returned;
                    AdjustTokenPrivileges(token, false, ref previous,
                        (uint)Marshal.SizeOf(typeof(TokenPrivileges)),
                        out ignored, out returned);
                }
                token.Dispose();
                throw;
            }
        }

        public void Dispose()
        {
            try
            {
                if (changed)
                {
                    TokenPrivileges ignored;
                    uint returned;
                    var restore = previous;
                    if (!AdjustTokenPrivileges(token, false, ref restore,
                        (uint)Marshal.SizeOf(typeof(TokenPrivileges)),
                        out ignored, out returned) ||
                        Marshal.GetLastWin32Error() != 0)
                        throw new PrivilegeRestoreFailure();
                }
            }
            finally { token.Dispose(); }
        }
    }

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--describe")
        {
            Console.WriteLine("SOURCE_ONLY:ONE_PIPE_READBACK_NO_CLIENT");
            return 0;
        }
        if (args.Length == 1 && args[0] == "--readback-flags")
        {
            Console.WriteLine(Ea4eProtectedPipeReadbackCandidate
                .RequestedSecurityInformation().ToString("x8"));
            return 0;
        }
        if (args.Length == 2 && args[0] == "--classify-readback")
            return ReadbackExit(args[1]);
        if (args.Length != 5 || args[0] != "--native-readback")
            return 2;

        Guid ceremony;
        DateTime deadline;
        if (!Guid.TryParseExact(args[3], "D", out ceremony) ||
            ceremony == Guid.Empty ||
            !DateTime.TryParseExact(args[4], "yyyy-MM-ddTHH:mm:ssZ",
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal |
                DateTimeStyles.AdjustToUniversal, out deadline))
            return Deny("INPUT");
        TimeSpan remaining = deadline - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero || remaining > TimeSpan.FromMinutes(2))
            return Deny("DEADLINE");

        string stage = "OPERATOR_TOKEN";
        try
        {
            var token = Ea4eProtectedIssuerToken.ReadCurrent();
            if (Ea4eProtectedIssuerToken.Evaluate(args[2], token)
                != "MATCH_ELEVATED_TOKEN")
                return Deny("OPERATOR_TOKEN");
            string name;
            string readback;
            stage = "PRIVILEGE_ENABLE";
            using (SecurityPrivilegeScope.Enable())
            {
                stage = "PIPE_CREATE";
                using (var pipe = Ea4eProtectedPipeCreatorCandidate.Open(
                    args[1], ceremony, out name))
                {
                    stage = "READBACK";
                    readback = Ea4eProtectedPipeReadbackCandidate.Read(
                        pipe, args[1]);
                }
                stage = "PRIVILEGE_RESTORE";
            }
            if (readback != "CANDIDATE:READBACK_STRUCTURE_ONLY")
                return ReadbackExit(readback);
            Console.WriteLine("CANDIDATE:READBACK_ONLY:" + name);
            return 0;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return Deny(error is PrivilegeRestoreFailure
                ? "PRIVILEGE_RESTORE" : stage == "READBACK"
                    ? "READBACK_EXCEPTION" : stage);
        }
    }

    private static int ReadbackExit(string result)
    {
        Console.WriteLine(result);
        switch (result)
        {
            case "DENY:READBACK_ACCESS_DENIED": return 18;
            case "DENY:READBACK_PRIVILEGE_NOT_HELD": return 19;
            case "DENY:READBACK_API_ERROR": return 20;
            case "DENY:READBACK_NULL_DESCRIPTOR": return 21;
            case "DENY:READBACK_INVALID_DESCRIPTOR": return 22;
            case "DENY:DESCRIPTOR_SIZE": return 23;
            case "DENY:OWNER_GROUP_OR_ACE_COUNT": return 24;
            case "DENY:UNREVIEWED_ACE": return 25;
            case "DENY:APP_ACE": return 26;
            case "DENY:DUPLICATE_SYSTEM_ACE": return 27;
            case "DENY:DUPLICATE_ADMIN_ACE": return 28;
            case "DENY:FOREIGN_ACE": return 29;
            case "DENY:REQUIRED_ACE_MISSING": return 30;
            case "DENY:DESCRIPTOR_SCREEN": return 31;
            case "DENY:INVALID_DESCRIPTOR": return 32;
            case "DENY:INVALID_HANDLE": return 33;
            case "DENY:APP_IDENTITY_NOT_INDIVIDUAL": return 36;
            case "DENY:APP_OWNER_OR_OWNER_MISSING": return 37;
            case "DENY:DACL_MISSING_OR_UNPROTECTED": return 38;
            case "DENY:LABEL_MISSING_OR_UNREVIEWED": return 39;
            case "DENY:APP_GRANT_NOT_EXACT": return 40;
            case "DENY:BROAD_ALLOW": return 41;
            case "DENY:UNTRUSTED_MUTATION_GRANT": return 42;
            case "DENY:APP_WRITE_MISSING": return 43;
            case "DENY:INVALID_INPUT": return 44;
            default: return 35;
        }
    }

    private static int Deny(string reason)
    {
        Console.WriteLine("DENY:" + reason);
        switch (reason)
        {
            case "INPUT": return 10;
            case "DEADLINE": return 11;
            case "OPERATOR_TOKEN": return 12;
            case "PRIVILEGE_ENABLE": return 13;
            case "PIPE_CREATE": return 14;
            case "READBACK": return 15;
            case "PRIVILEGE_RESTORE": return 16;
            case "READBACK_EXCEPTION": return 34;
            default: return 17;
        }
    }
}
