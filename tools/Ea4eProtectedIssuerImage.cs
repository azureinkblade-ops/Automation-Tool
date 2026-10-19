// Read-only executable identity witness; a protected install is still required.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

internal static class Ea4eProtectedIssuerImage
{
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");

    internal sealed class Observation
    {
        internal readonly string Path;
        internal readonly string Sha256;

        internal Observation(string path, string sha256)
        {
            Path = path;
            Sha256 = sha256;
        }
    }

    internal static Observation ReadCurrent()
    {
        using (Process process = Process.GetCurrentProcess())
        {
            string path = process.MainModule.FileName;
            if (String.IsNullOrWhiteSpace(path) || !System.IO.Path.IsPathRooted(path))
                throw new InvalidOperationException("Executable path unavailable");
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                                               FileShare.Read))
            using (var sha = SHA256.Create())
            {
                string digest = BitConverter.ToString(sha.ComputeHash(stream))
                    .Replace("-", "").ToLowerInvariant();
                return new Observation(path, digest);
            }
        }
    }

    internal static string Evaluate(string expectedPath, string expectedSha256,
                                    Observation observed)
    {
        if (String.IsNullOrWhiteSpace(expectedPath)
            || !System.IO.Path.IsPathRooted(expectedPath)
            || expectedSha256 == null || !Hex.IsMatch(expectedSha256))
            return "EXPECTED_IMAGE_INVALID";
        if (observed == null || String.IsNullOrWhiteSpace(observed.Path)
            || !System.IO.Path.IsPathRooted(observed.Path)
            || observed.Sha256 == null || !Hex.IsMatch(observed.Sha256))
            return "IMAGE_OBSERVATION_INVALID";
        if (!String.Equals(System.IO.Path.GetFullPath(expectedPath),
                           System.IO.Path.GetFullPath(observed.Path),
                           StringComparison.OrdinalIgnoreCase))
            return "IMAGE_PATH_MISMATCH";
        if (!String.Equals(expectedSha256, observed.Sha256,
                           StringComparison.Ordinal))
            return "IMAGE_HASH_MISMATCH";
        return "MATCH_IMAGE_BYTES";
    }
}
