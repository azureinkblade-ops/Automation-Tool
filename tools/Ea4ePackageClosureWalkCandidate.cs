// Read-only package closure walk. Enumeration is not a protected authority witness.
using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4ePackageClosureWalkCandidate
{
    private const int MaxEntries = 50000;
    private const int MaxDepth = 64;

    private static bool CanonicalRelative(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > 1024
            || value.IndexOf('\\') >= 0 || value.IndexOf(':') >= 0)
            return false;
        foreach (string part in value.Split('/'))
        {
            if (part.Length == 0 || part == "." || part == ".."
                || part.EndsWith(".", StringComparison.Ordinal)
                || part.EndsWith(" ", StringComparison.Ordinal))
                return false;
            foreach (char character in part)
                if (!(character >= 'a' && character <= 'z')
                    && !(character >= 'A' && character <= 'Z')
                    && !(character >= '0' && character <= '9')
                    && character != '_' && character != '-' && character != '.'
                    && character != ' ')
                    return false;
            string stem = part.Split('.')[0].ToUpperInvariant();
            if (stem == "CON" || stem == "PRN" || stem == "AUX" || stem == "NUL"
                || (stem.Length == 4 && (stem.StartsWith("COM") || stem.StartsWith("LPT"))
                    && stem[3] >= '1' && stem[3] <= '9'))
                return false;
        }
        return true;
    }

    internal static string Denial(string root, IDictionary<string, string> expected)
    {
        if (expected == null || expected.Count == 0 || expected.Count > MaxEntries)
            return "EXPECTED_MANIFEST_INVALID";
        var wanted = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var wantedSpellings = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var wantedDirectories = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (KeyValuePair<string, string> pair in expected)
        {
            if (!CanonicalRelative(pair.Key)
                || !Ea4eProtectedByteSnapshotCandidate.IsCanonicalHash(pair.Value)
                || wanted.ContainsKey(pair.Key))
                return "EXPECTED_MANIFEST_INVALID";
            wanted.Add(pair.Key, pair.Value);
            wantedSpellings.Add(pair.Key, pair.Key);
            string[] parts = pair.Key.Split('/');
            for (int index = 1; index < parts.Length; index++)
            {
                string directory = String.Join("/", parts, 0, index);
                string prior;
                if (wantedDirectories.TryGetValue(directory, out prior)
                    && !String.Equals(directory, prior, StringComparison.Ordinal))
                    return "EXPECTED_MANIFEST_INVALID";
                wantedDirectories[directory] = directory;
            }
        }
        foreach (string directory in wantedDirectories.Keys)
            if (wanted.ContainsKey(directory)) return "EXPECTED_MANIFEST_INVALID";
        if (String.IsNullOrEmpty(root)) return "ROOT_INVALID";
        string rootDenial = Ea4eProtectedPathTopologyCandidate.DenialDirectory(root);
        if (rootDenial != null) return rootDenial;
        if (!Directory.Exists(root)) return "ROOT_NOT_DIRECTORY";
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var pending = new Stack<Tuple<string, string, int>>();
        pending.Push(Tuple.Create(root, "", 0));
        int entries = 0;
        try
        {
            while (pending.Count != 0)
            {
                var directory = pending.Pop();
                foreach (string path in Directory.EnumerateFileSystemEntries(directory.Item1))
                {
                    if (++entries > MaxEntries) return "ENTRY_LIMIT_EXCEEDED";
                    string name = Path.GetFileName(path);
                    string relative = directory.Item2.Length == 0
                        ? name : directory.Item2 + "/" + name;
                    if (!CanonicalRelative(relative)) return "OBSERVED_PATH_INVALID";
                    bool isDirectory = Directory.Exists(path);
                    string topology = isDirectory
                        ? Ea4eProtectedPathTopologyCandidate.DenialDirectory(path)
                        : Ea4eProtectedPathTopologyCandidate.Denial(path);
                    if (topology != null) return topology;
                    if (isDirectory)
                    {
                        string expectedDirectory;
                        if (!wantedDirectories.TryGetValue(relative, out expectedDirectory)
                            || !String.Equals(relative, expectedDirectory,
                                StringComparison.Ordinal))
                            return "UNEXPECTED_DIRECTORY";
                        if (directory.Item3 >= MaxDepth) return "DEPTH_LIMIT_EXCEEDED";
                        pending.Push(Tuple.Create(path, relative, directory.Item3 + 1));
                    }
                    else if (File.Exists(path))
                    {
                        string digest;
                        string expectedPath;
                        if (!wanted.TryGetValue(relative, out digest)
                            || !wantedSpellings.TryGetValue(relative, out expectedPath)
                            || !String.Equals(relative, expectedPath,
                                StringComparison.Ordinal)
                            || !seen.Add(relative))
                            return "UNEXPECTED_OR_DUPLICATE_FILE";
                        string bytes = Ea4eProtectedByteSnapshotCandidate.Denial(path, digest);
                        if (bytes != null) return bytes;
                    }
                    else return "ENTRY_TYPE_UNAVAILABLE";
                }
            }
        }
        catch
        {
            return "ENUMERATION_UNAVAILABLE";
        }
        return seen.Count == wanted.Count ? null : "EXPECTED_FILE_MISSING";
    }
}
