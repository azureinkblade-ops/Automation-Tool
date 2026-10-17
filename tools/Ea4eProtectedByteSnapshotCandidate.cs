// Read-only byte observation. A match is not mapped-image or issuer proof.
using System;
using System.IO;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedByteSnapshotCandidate
{
    private const long MaxBytes = 64L * 1024 * 1024;

    internal static string Denial(string path, string expectedSha256)
    {
        if (!IsCanonicalHash(expectedSha256)) return "EXPECTED_HASH_INVALID";

        return Ea4eProtectedPathTopologyCandidate.DenialWithReadableLeaf(
            path, (handle, objectPath, directory) =>
                directory ? null : CheckBytes(handle, expectedSha256));
    }

    internal static bool IsCanonicalHash(string expectedSha256)
    {
        if (expectedSha256 == null || expectedSha256.Length != 64)
            return false;
        foreach (char digit in expectedSha256)
            if (!((digit >= '0' && digit <= '9') ||
                  (digit >= 'a' && digit <= 'f')))
                return false;
        return true;
    }

    internal static string CheckBytes(SafeFileHandle handle, string expectedSha256)
    {
        try
        {
            // The wrapper must not close the topology owner's retained handle.
            using (var borrowed = new SafeFileHandle(handle.DangerousGetHandle(), false))
            using (var stream = new FileStream(borrowed, FileAccess.Read))
            using (var hash = SHA256.Create())
            {
                long initialLength = stream.Length;
                if (initialLength > MaxBytes) return "BYTE_LIMIT_EXCEEDED";
                var buffer = new byte[65536];
                long total = 0;
                int count;
                while ((count = stream.Read(buffer, 0, buffer.Length)) != 0)
                {
                    total += count;
                    if (total > MaxBytes) return "BYTE_LIMIT_EXCEEDED";
                    hash.TransformBlock(buffer, 0, count, buffer, 0);
                }
                hash.TransformFinalBlock(new byte[0], 0, 0);
                if (total != initialLength || stream.Length != initialLength)
                    return "BYTE_LENGTH_CHANGED";
                string actual = BitConverter.ToString(hash.Hash).Replace("-", "").ToLowerInvariant();
                return String.Equals(actual, expectedSha256, StringComparison.Ordinal)
                    ? null : "BYTE_HASH_MISMATCH";
            }
        }
        catch
        {
            return "BYTE_READ_UNAVAILABLE";
        }
    }
}
