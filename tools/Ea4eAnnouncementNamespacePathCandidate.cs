// Value-only preflight; callers must independently authenticate both inputs.
using System;
using System.IO;

internal static class Ea4eAnnouncementNamespacePathCandidate
{
    private const string Suffix = @"Hermes\EA4E\IssuerAnnouncements\v1";

    private static bool CanonicalLocalPath(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > 32767 ||
            value.Length < 4 || !Char.IsLetter(value[0]) ||
            value[1] != ':' || value[2] != (char)92 ||
            value.IndexOf(':', 2) >= 0 || value.IndexOf('/') >= 0 ||
            value.EndsWith(@"\", StringComparison.Ordinal))
            return false;
        try
        {
            if (!String.Equals(Path.GetFullPath(value), value,
                               StringComparison.OrdinalIgnoreCase))
                return false;
            string root = Path.GetPathRoot(value);
            foreach (string part in value.Substring(root.Length).Split((char)92))
                if (part.Length == 0 || part == "." || part == "..")
                    return false;
            return true;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return false;
        }
    }

    internal static string Screen(string resolvedKnownFolder,
                                  string pinnedManifestRoot,
                                  out string expectedRoot)
    {
        expectedRoot = null;
        if (!CanonicalLocalPath(resolvedKnownFolder))
            return "DENY:KNOWN_FOLDER_FORM";
        if (!CanonicalLocalPath(pinnedManifestRoot))
            return "DENY:MANIFEST_FORM";
        string candidate = Path.Combine(resolvedKnownFolder, Suffix);
        if (!String.Equals(candidate, pinnedManifestRoot,
                           StringComparison.OrdinalIgnoreCase))
            return "DENY:MANIFEST_MISMATCH";
        expectedRoot = candidate;
        return null;
    }
}
