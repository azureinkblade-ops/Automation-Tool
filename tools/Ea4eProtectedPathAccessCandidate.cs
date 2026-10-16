// Non-authorizing Windows ACL observation using retained topology handles.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedPathAccessCandidate
{
    private const uint TokenQuery = 0x0008;
    private const uint TokenDuplicate = 0x0002;
    private const uint MaximumAllowed = 0x02000000;
    private const uint ClosureMutationRights = 0x000D0156;
    private const uint AncestorReplacementRights = 0x000D0152;

    internal static bool GrantsMutation(bool inClosure, uint granted)
    {
        uint blocked = inClosure ? ClosureMutationRights
                                 : AncestorReplacementRights;
        return (granted & blocked) != 0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct GenericMapping
    {
        internal uint Read;
        internal uint Write;
        internal uint Execute;
        internal uint All;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(
        IntPtr process, uint access, out SafeFileHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DuplicateToken(
        SafeFileHandle existing, int impersonationLevel,
        out SafeFileHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(
        SafeFileHandle token, int informationClass, out int information,
        uint length, out uint returned);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern uint GetSecurityInfo(
        SafeFileHandle handle, int objectType, uint information,
        out IntPtr owner, out IntPtr group, out IntPtr dacl,
        IntPtr sacl, out IntPtr descriptor);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true,
        EntryPoint = "ConvertSidToStringSidW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ConvertSidToStringSid(
        IntPtr sid, out IntPtr stringSid);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AccessCheck(
        IntPtr descriptor, SafeFileHandle token, uint desired,
        ref GenericMapping mapping, IntPtr privileges,
        ref uint privilegeLength, out uint granted,
        [MarshalAs(UnmanagedType.Bool)] out bool status);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    private static string OwnerSid(IntPtr owner)
    {
        IntPtr text = IntPtr.Zero;
        try
        {
            if (owner == IntPtr.Zero || !ConvertSidToStringSid(owner, out text))
                return null;
            return Marshal.PtrToStringUni(text);
        }
        finally
        {
            if (text != IntPtr.Zero) LocalFree(text);
        }
    }

    private static string CheckHandle(
        SafeFileHandle handle, SafeFileHandle appToken, string appSid,
        bool inClosure)
    {
        IntPtr owner;
        IntPtr group;
        IntPtr dacl;
        IntPtr descriptor;
        uint result = GetSecurityInfo(handle, 1, 0x7, out owner, out group,
                                      out dacl, IntPtr.Zero, out descriptor);
        if (result != 0 || descriptor == IntPtr.Zero)
            return "SECURITY_DESCRIPTOR_UNAVAILABLE";
        try
        {
            if (owner == IntPtr.Zero || group == IntPtr.Zero || dacl == IntPtr.Zero)
                return "SECURITY_DESCRIPTOR_INCOMPLETE";
            string ownerSid = OwnerSid(owner);
            if (ownerSid == null) return "OWNER_UNAVAILABLE";
            if (String.Equals(ownerSid, appSid, StringComparison.OrdinalIgnoreCase))
                return "APP_OWNS_OBJECT";

            var mapping = new GenericMapping {
                Read = 0x00120089, Write = 0x00120116,
                Execute = 0x001200A0, All = 0x001F01FF
            };
            uint privilegeLength = 1024;
            IntPtr privileges = Marshal.AllocHGlobal((int)privilegeLength);
            try
            {
                uint granted;
                bool accessStatus;
                bool ok = AccessCheck(descriptor, appToken, MaximumAllowed,
                    ref mapping, privileges, ref privilegeLength,
                    out granted, out accessStatus);
                if (!ok && Marshal.GetLastWin32Error() == 122
                    && privilegeLength > 1024 && privilegeLength <= 65536)
                {
                    Marshal.FreeHGlobal(privileges);
                    privileges = IntPtr.Zero;
                    privileges = Marshal.AllocHGlobal((int)privilegeLength);
                    ok = AccessCheck(descriptor, appToken, MaximumAllowed,
                        ref mapping, privileges, ref privilegeLength,
                        out granted, out accessStatus);
                }
                if (!ok) return "ACCESS_CHECK_UNAVAILABLE_" + Marshal.GetLastWin32Error();
                if (!accessStatus) return "APP_ACCESS_DENIED";
                if (GrantsMutation(inClosure, granted))
                    return "APP_MUTATION_RIGHTS";
                return null;
            }
            finally
            {
                if (privileges != IntPtr.Zero) Marshal.FreeHGlobal(privileges);
            }
        }
        finally
        {
            LocalFree(descriptor);
        }
    }

    internal static string DenialForCurrentUnelevatedApp(
        string path, string protectedRoot, string expectedAppSid)
    {
        if (String.IsNullOrEmpty(expectedAppSid)) return "APP_IDENTITY_UNBOUND";
        string root;
        try
        {
            root = Path.GetFullPath(protectedRoot);
            if (!String.Equals(root, protectedRoot, StringComparison.OrdinalIgnoreCase)
                || String.Equals(root, Path.GetPathRoot(root),
                                 StringComparison.OrdinalIgnoreCase)
                || !path.StartsWith(root.TrimEnd('\\') + "\\",
                                    StringComparison.OrdinalIgnoreCase))
                return "PROTECTED_ROOT_UNBOUND";
        }
        catch { return "PROTECTED_ROOT_UNBOUND"; }
        SafeFileHandle primary;
        if (!OpenProcessToken(GetCurrentProcess(), TokenQuery | TokenDuplicate,
                              out primary))
            return "APP_TOKEN_UNAVAILABLE";
        using (primary)
        {
            try
            {
                string actualSid;
                using (var identity = new WindowsIdentity(primary.DangerousGetHandle()))
                    actualSid = identity.User.Value;
                if (!String.Equals(actualSid, expectedAppSid,
                                   StringComparison.OrdinalIgnoreCase))
                    return "APP_IDENTITY_MISMATCH";
                int elevated;
                uint returned;
                if (!GetTokenInformation(primary, 20, out elevated, 4, out returned)
                    || returned != 4 || elevated != 0)
                    return "APP_TOKEN_NOT_UNELEVATED";
                SafeFileHandle impersonation;
                if (!DuplicateToken(primary, 2, out impersonation))
                    return "APP_IMPERSONATION_UNAVAILABLE";
                using (impersonation)
                {
                    return Ea4eProtectedPathTopologyCandidate.Denial(
                        path, (handle, objectPath, directory) =>
                            CheckHandle(handle, impersonation, actualSid,
                                String.Equals(objectPath, root,
                                              StringComparison.OrdinalIgnoreCase)
                                || objectPath.StartsWith(root.TrimEnd('\\') + "\\",
                                    StringComparison.OrdinalIgnoreCase)));
                }
            }
            catch
            {
                return "ACCESS_OBSERVATION_UNAVAILABLE";
            }
        }
    }
}
