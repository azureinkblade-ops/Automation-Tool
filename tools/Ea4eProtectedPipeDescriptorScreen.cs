// Static descriptor screen only. Effective access requires a native token probe.
using System;
using System.Security.AccessControl;
using System.Security.Principal;

internal static class Ea4eProtectedPipeDescriptorScreen
{
    private const int FileWriteData = 0x00000002;
    private const int FileCreatePipeInstance = 0x00000004;
    private const int WriteDac = 0x00040000;
    private const int WriteOwner = 0x00080000;
    private const int GenericWrite = unchecked((int)0x40000000);
    private const int GenericAll = unchecked((int)0x10000000);
    private const int Dangerous = FileCreatePipeInstance | WriteDac |
        WriteOwner | GenericWrite | GenericAll;

    internal static string Screen(string sddl, string appSidText)
    {
        RawSecurityDescriptor descriptor;
        try
        {
            descriptor = new RawSecurityDescriptor(sddl);
        }
        catch (ArgumentException)
        {
            return "DENY:INVALID_INPUT";
        }
        return ScreenDescriptor(descriptor, appSidText);
    }

    internal static string ScreenDescriptor(RawSecurityDescriptor descriptor,
                                             string appSidText)
    {
        SecurityIdentifier appSid;
        try
        {
            appSid = new SecurityIdentifier(appSidText);
        }
        catch (ArgumentException)
        {
            return "DENY:INVALID_INPUT";
        }
        if (descriptor == null)
            return "DENY:INVALID_INPUT";

        if (IsBroadTrustee(appSid) ||
            appSid.IsWellKnown(WellKnownSidType.LocalSystemSid) ||
            appSid.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid))
            return "DENY:APP_IDENTITY_NOT_INDIVIDUAL";

        if (descriptor.Owner == null || descriptor.Owner.Equals(appSid))
            return "DENY:APP_OWNER_OR_OWNER_MISSING";
        if (descriptor.DiscretionaryAcl == null ||
            (descriptor.ControlFlags & ControlFlags.DiscretionaryAclProtected) == 0)
            return "DENY:DACL_MISSING_OR_UNPROTECTED";
        if (!HasExactMediumLabel(descriptor))
            return "DENY:LABEL_MISSING_OR_UNREVIEWED";

        bool appWrite = false;
        foreach (GenericAce ace in descriptor.DiscretionaryAcl)
        {
            CommonAce common = ace as CommonAce;
            if (common == null || common.IsCallback ||
                common.AceFlags != AceFlags.None ||
                (common.AceQualifier != AceQualifier.AccessAllowed &&
                 common.AceQualifier != AceQualifier.AccessDenied))
                return "DENY:UNREVIEWED_ACE";
            if (common.AceQualifier == AceQualifier.AccessDenied)
                continue;

            SecurityIdentifier sid = common.SecurityIdentifier;
            if (sid.Equals(appSid))
            {
                if (common.AccessMask != FileWriteData || appWrite)
                    return "DENY:APP_GRANT_NOT_EXACT";
                appWrite = true;
                continue;
            }

            if (IsBroadTrustee(sid))
                return "DENY:BROAD_ALLOW";

            if ((common.AccessMask & Dangerous) != 0 &&
                !sid.IsWellKnown(WellKnownSidType.LocalSystemSid) &&
                !sid.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid))
                return "DENY:UNTRUSTED_MUTATION_GRANT";
        }

        return appWrite ? "CANDIDATE:STATIC_ONLY" : "DENY:APP_WRITE_MISSING";
    }

    private static bool IsBroadTrustee(SecurityIdentifier sid)
    {
        return sid.IsWellKnown(WellKnownSidType.WorldSid) ||
            sid.IsWellKnown(WellKnownSidType.AuthenticatedUserSid) ||
            sid.IsWellKnown(WellKnownSidType.BuiltinUsersSid) ||
            sid.IsWellKnown(WellKnownSidType.InteractiveSid) ||
            sid.IsWellKnown(WellKnownSidType.CreatorOwnerSid);
    }

    private static bool HasExactMediumLabel(RawSecurityDescriptor descriptor)
    {
        if (descriptor.SystemAcl == null || descriptor.SystemAcl.Count != 1)
            return false;
        CustomAce label = descriptor.SystemAcl[0] as CustomAce;
        if (label == null || (byte)label.AceType != 0x11 ||
            label.AceFlags != AceFlags.None)
            return false;
        byte[] opaque = label.GetOpaque();
        if (opaque.Length < 12 || BitConverter.ToUInt32(opaque, 0) != 1)
            return false;
        try
        {
            SecurityIdentifier sid = new SecurityIdentifier(opaque, 4);
            return opaque.Length == 4 + sid.BinaryLength &&
                sid.Value == "S-1-16-8192";
        }
        catch (ArgumentException)
        {
            return false;
        }
    }
}
