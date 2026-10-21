// Source-only retained file descriptor readback; native Read is not qualified.
using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;

internal static class Ea4eAnnouncementFileDescriptorCandidate
{
    private const int SeFileObject = 1;
    private const uint OwnerGroupDaclSaclLabel = 0x0000001f;
    private const int AppReadOnly = 0x00020081;
    private const int AppDirectoryReadTraverse = 0x000200a1;
    private const int TrustedFileAll = 0x001f01ff;

    [DllImport("advapi32.dll", ExactSpelling = true)]
    private static extern uint GetSecurityInfo(
        SafeHandle handle, int objectType, uint securityInformation,
        IntPtr owner, IntPtr group, IntPtr dacl, IntPtr sacl,
        out IntPtr descriptor);

    [DllImport("advapi32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsValidSecurityDescriptor(IntPtr descriptor);

    [DllImport("advapi32.dll", ExactSpelling = true)]
    private static extern uint GetSecurityDescriptorLength(IntPtr descriptor);

    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern IntPtr LocalFree(IntPtr memory);

    internal static uint RequestedSecurityInformation()
    {
        return OwnerGroupDaclSaclLabel;
    }

    internal static string ScreenSddl(string sddl, string appSidText)
    {
        return ScreenSddlCore(sddl, appSidText, AppReadOnly,
                              "CANDIDATE:FILE_DESCRIPTOR_STRUCTURE_ONLY");
    }

    internal static string ScreenDirectorySddl(string sddl, string appSidText)
    {
        return ScreenSddlCore(sddl, appSidText, AppDirectoryReadTraverse,
                              "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY");
    }

    private static string ScreenSddlCore(string sddl, string appSidText,
                                         int appAccess, string success)
    {
        try { return ScreenDescriptor(new RawSecurityDescriptor(sddl),
                                      appSidText, appAccess, success); }
        catch (SystemException error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:INVALID_DESCRIPTOR";
        }
    }

    private static string ScreenDescriptor(RawSecurityDescriptor descriptor,
                                           string appSidText, int appAccess,
                                           string success)
    {
        SecurityIdentifier app;
        try { app = new SecurityIdentifier(appSidText); }
        catch (ArgumentException) { return "DENY:INVALID_APP_SID"; }
        var admin = new SecurityIdentifier(
            WellKnownSidType.BuiltinAdministratorsSid, null);
        var system = new SecurityIdentifier(
            WellKnownSidType.LocalSystemSid, null);
        if (app.Equals(admin) || app.Equals(system) ||
            app.IsWellKnown(WellKnownSidType.WorldSid) ||
            app.IsWellKnown(WellKnownSidType.AuthenticatedUserSid) ||
            app.IsWellKnown(WellKnownSidType.BuiltinUsersSid))
            return "DENY:APP_IDENTITY";
        if (descriptor.Owner == null || !descriptor.Owner.Equals(admin) ||
            descriptor.Group == null || !descriptor.Group.Equals(admin) ||
            descriptor.DiscretionaryAcl == null ||
            (descriptor.ControlFlags & ControlFlags.DiscretionaryAclProtected) == 0 ||
            descriptor.DiscretionaryAcl.Count != 3)
            return "DENY:OWNER_OR_DACL";

        bool appSeen = false, adminSeen = false, systemSeen = false;
        foreach (GenericAce ace in descriptor.DiscretionaryAcl)
        {
            CommonAce allow = ace as CommonAce;
            if (allow == null || allow.IsCallback ||
                allow.AceQualifier != AceQualifier.AccessAllowed ||
                allow.AceFlags != AceFlags.None)
                return "DENY:UNREVIEWED_DACL_ACE";
            if (allow.SecurityIdentifier.Equals(app))
            {
                if (appSeen || allow.AccessMask != appAccess)
                    return "DENY:APP_ACCESS";
                appSeen = true;
            }
            else if (allow.SecurityIdentifier.Equals(admin))
            {
                if (adminSeen || allow.AccessMask != TrustedFileAll)
                    return "DENY:ADMIN_ACCESS";
                adminSeen = true;
            }
            else if (allow.SecurityIdentifier.Equals(system))
            {
                if (systemSeen || allow.AccessMask != TrustedFileAll)
                    return "DENY:SYSTEM_ACCESS";
                systemSeen = true;
            }
            else return "DENY:FOREIGN_DACL_ACE";
        }
        if (!appSeen || !adminSeen || !systemSeen)
            return "DENY:REQUIRED_ACE_MISSING";
        if (descriptor.SystemAcl == null || descriptor.SystemAcl.Count != 1)
            return "DENY:LABEL_MISSING";
        CustomAce label = descriptor.SystemAcl[0] as CustomAce;
        if (label == null || (byte)label.AceType != 0x11 ||
            label.AceFlags != AceFlags.None)
            return "DENY:UNREVIEWED_LABEL";
        byte[] opaque = label.GetOpaque();
        if (opaque.Length < 12 || BitConverter.ToUInt32(opaque, 0) != 1)
            return "DENY:LABEL_POLICY";
        try
        {
            var sid = new SecurityIdentifier(opaque, 4);
            if (opaque.Length != 4 + sid.BinaryLength ||
                sid.Value != "S-1-16-12288")
                return "DENY:LABEL_IDENTITY";
        }
        catch (ArgumentException) { return "DENY:LABEL_IDENTITY"; }
        return success;
    }

    internal static string ScreenBytes(byte[] bytes, string appSidText)
    {
        return ScreenBytesCore(bytes, appSidText, AppReadOnly,
                               "CANDIDATE:FILE_DESCRIPTOR_STRUCTURE_ONLY");
    }

    internal static string ScreenDirectoryBytes(byte[] bytes, string appSidText)
    {
        return ScreenBytesCore(bytes, appSidText, AppDirectoryReadTraverse,
                               "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY");
    }

    private static string ScreenBytesCore(byte[] bytes, string appSidText,
                                          int appAccess, string success)
    {
        if (bytes == null || bytes.Length < 20 || bytes.Length > 8192)
            return "DENY:DESCRIPTOR_SIZE";
        try
        {
            var descriptor = new RawSecurityDescriptor(bytes, 0);
            if (descriptor.BinaryLength != bytes.Length)
                return "DENY:DESCRIPTOR_TRAILING_BYTES";
            return ScreenDescriptor(descriptor, appSidText, appAccess, success);
        }
        catch (SystemException error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:INVALID_DESCRIPTOR";
        }
    }

    // Caller retains this exact handle and scopes enabled SeSecurityPrivilege.
    internal static string Read(SafeHandle handle, string appSidText,
                                out byte[] bytes)
    {
        return ReadCore(handle, appSidText, false, out bytes);
    }

    internal static string ReadDirectory(SafeHandle handle,
                                         string appSidText, out byte[] bytes)
    {
        return ReadCore(handle, appSidText, true, out bytes);
    }

    private static string ReadCore(SafeHandle handle, string appSidText,
                                   bool directory, out byte[] bytes)
    {
        bytes = null;
        if (handle == null || handle.IsInvalid || handle.IsClosed)
            return "DENY:INVALID_HANDLE";
        IntPtr descriptor = IntPtr.Zero;
        try
        {
            uint status = GetSecurityInfo(handle, SeFileObject,
                RequestedSecurityInformation(), IntPtr.Zero, IntPtr.Zero,
                IntPtr.Zero, IntPtr.Zero, out descriptor);
            if (status == 5) return "DENY:ACCESS_DENIED";
            if (status == 1314) return "DENY:PRIVILEGE_NOT_HELD";
            if (status != 0 || descriptor == IntPtr.Zero ||
                !IsValidSecurityDescriptor(descriptor))
                return "DENY:DESCRIPTOR_UNAVAILABLE";
            uint length = GetSecurityDescriptorLength(descriptor);
            if (length < 20 || length > 8192) return "DENY:DESCRIPTOR_SIZE";
            byte[] observed = new byte[length];
            Marshal.Copy(descriptor, observed, 0, checked((int)length));
            string result = directory
                ? ScreenDirectoryBytes(observed, appSidText)
                : ScreenBytes(observed, appSidText);
            if (result == (directory
                ? "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY"
                : "CANDIDATE:FILE_DESCRIPTOR_STRUCTURE_ONLY"))
                bytes = observed;
            return result;
        }
        finally
        {
            if (descriptor != IntPtr.Zero) LocalFree(descriptor);
        }
    }
}
