// Value-only installer plan. Callers must authenticate the manifest and SID.
using System;
using System.IO;

internal static class Ea4eDirectoryInstallPlanCandidate
{
    internal const uint DisallowPathRedirects = 1;
    internal const uint ShareReadWriteNoDelete = 3;
    internal const uint DirectoryReadbackAccess = 0x012200a1;

    internal static string Build(string resolvedProgramData,
                                 string pinnedManifestRoot, string appSid,
                                 out string[] components, out string sddl)
    {
        components = null;
        sddl = null;
        string root;
        string denial = Ea4eAnnouncementNamespacePathCandidate.Screen(
            resolvedProgramData, pinnedManifestRoot, out root);
        if (denial != null) return denial;
        string candidate = "O:BAG:BAD:P(A;;0x000200a1;;;" + appSid +
            ")(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)";
        if (Ea4eAnnouncementFileDescriptorCandidate.ScreenDirectorySddl(
                candidate, appSid) !=
            "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY")
            return "DENY:DIRECTORY_DESCRIPTOR";
        string first = Path.Combine(resolvedProgramData, "Hermes");
        string second = Path.Combine(first, "EA4E");
        string third = Path.Combine(second, "IssuerAnnouncements");
        string fourth = Path.Combine(third, "v1");
        if (!String.Equals(fourth, root, StringComparison.OrdinalIgnoreCase))
            return "DENY:COMPONENT_MISMATCH";
        components = new[] { first, second, third, fourth };
        sddl = candidate;
        return null;
    }
}
