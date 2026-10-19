// Source-only handle readback candidate. Native Read is not qualified for use.
using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedPipeReadbackCandidate
{
    private const int SeKernelObject = 6;
    private const uint OwnerGroupDaclSacl = 0x0000000f;

    [DllImport("advapi32.dll", ExactSpelling = true)]
    private static extern uint GetSecurityInfo(
        SafePipeHandle handle, int objectType, uint securityInformation,
        IntPtr owner, IntPtr group, IntPtr dacl, IntPtr sacl,
        out IntPtr descriptor);

    [DllImport("advapi32.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsValidSecurityDescriptor(IntPtr descriptor);

    [DllImport("advapi32.dll", ExactSpelling = true)]
    private static extern uint GetSecurityDescriptorLength(IntPtr descriptor);

    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern IntPtr LocalFree(IntPtr memory);

    internal static string ScreenBytes(byte[] bytes, string appSidText)
    {
        if (bytes == null || bytes.Length < 20 || bytes.Length > 8192)
            return "DENY:DESCRIPTOR_SIZE";
        try
        {
            var descriptor = new RawSecurityDescriptor(bytes, 0);
            var administrators = new SecurityIdentifier(
                WellKnownSidType.BuiltinAdministratorsSid, null);
            var system = new SecurityIdentifier(
                WellKnownSidType.LocalSystemSid, null);
            var app = new SecurityIdentifier(appSidText);
            if (descriptor.Owner == null || !descriptor.Owner.Equals(administrators)
                || descriptor.Group == null || !descriptor.Group.Equals(administrators)
                || descriptor.DiscretionaryAcl == null
                || descriptor.DiscretionaryAcl.Count != 3)
                return "DENY:OWNER_GROUP_OR_ACE_COUNT";
            bool appSeen = false, systemSeen = false, adminSeen = false;
            foreach (GenericAce ace in descriptor.DiscretionaryAcl)
            {
                var allowed = ace as CommonAce;
                if (allowed == null || allowed.IsCallback
                    || allowed.AceQualifier != AceQualifier.AccessAllowed
                    || allowed.AceFlags != AceFlags.None
                    || allowed.AccessMask == 0)
                    return "DENY:UNREVIEWED_ACE";
                if (allowed.SecurityIdentifier.Equals(app))
                {
                    if (appSeen || allowed.AccessMask != 0x00000002)
                        return "DENY:APP_ACE";
                    appSeen = true;
                }
                else if (allowed.SecurityIdentifier.Equals(system))
                {
                    if (systemSeen) return "DENY:DUPLICATE_SYSTEM_ACE";
                    systemSeen = true;
                }
                else if (allowed.SecurityIdentifier.Equals(administrators))
                {
                    if (adminSeen) return "DENY:DUPLICATE_ADMIN_ACE";
                    adminSeen = true;
                }
                else return "DENY:FOREIGN_ACE";
            }
            if (!appSeen || !systemSeen || !adminSeen)
                return "DENY:REQUIRED_ACE_MISSING";
            string screen = Ea4eProtectedPipeDescriptorScreen.ScreenDescriptor(
                descriptor, appSidText);
            return screen == "CANDIDATE:STATIC_ONLY"
                ? "CANDIDATE:READBACK_STRUCTURE_ONLY" : screen;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:INVALID_DESCRIPTOR";
        }
    }

    // Requires an exact live authorization, an enabled SeSecurityPrivilege,
    // and the retained creator handle opened with ACCESS_SYSTEM_SECURITY.
    internal static string Read(SafePipeHandle handle, string appSidText)
    {
        if (handle == null || handle.IsInvalid || handle.IsClosed)
            return "DENY:INVALID_HANDLE";
        IntPtr descriptor = IntPtr.Zero;
        try
        {
            uint status = GetSecurityInfo(handle, SeKernelObject,
                OwnerGroupDaclSacl, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero,
                IntPtr.Zero, out descriptor);
            if (status == 5) return "DENY:READBACK_ACCESS_DENIED";
            if (status == 1314) return "DENY:READBACK_PRIVILEGE_NOT_HELD";
            if (status != 0) return "DENY:READBACK_API_ERROR";
            if (descriptor == IntPtr.Zero) return "DENY:READBACK_NULL_DESCRIPTOR";
            if (!IsValidSecurityDescriptor(descriptor))
                return "DENY:READBACK_INVALID_DESCRIPTOR";
            uint length = GetSecurityDescriptorLength(descriptor);
            if (length < 20 || length > 8192)
                return "DENY:DESCRIPTOR_SIZE";
            byte[] bytes = new byte[length];
            Marshal.Copy(descriptor, bytes, 0, checked((int)length));
            return ScreenBytes(bytes, appSidText);
        }
        finally
        {
            if (descriptor != IntPtr.Zero)
                LocalFree(descriptor);
        }
    }
}
