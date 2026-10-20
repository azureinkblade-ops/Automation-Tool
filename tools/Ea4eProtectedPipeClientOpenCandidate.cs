// Source-only client open candidate; native Open needs a bounded ceremony.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedPipeClientOpenCandidate
{
    private const string Prefix = @"\\.\pipe\ea4e-issuer-";
    private const uint OpenExisting = 3;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
        EntryPoint = "CreateFileW")]
    private static extern SafeFileHandle CreateFile(
        string name, uint desiredAccess, uint shareMode, IntPtr attributes,
        uint disposition, uint flags, IntPtr template);

    internal static string NameDenial(string name)
    {
        if (String.IsNullOrEmpty(name) || !name.StartsWith(Prefix,
            StringComparison.Ordinal) || name.Length != Prefix.Length + 65 ||
            name[Prefix.Length + 32] != '-')
            return "DENY:PIPE_NAME_SHAPE";
        string ceremonyText = name.Substring(Prefix.Length, 32);
        string randomText = name.Substring(Prefix.Length + 33, 32);
        Guid ceremony, random;
        if (!Guid.TryParseExact(ceremonyText, "N", out ceremony) ||
            !Guid.TryParseExact(randomText, "N", out random) ||
            ceremony == Guid.Empty || random == Guid.Empty ||
            ceremony == random ||
            ceremony.ToString("N") != ceremonyText ||
            random.ToString("N") != randomText)
            return "DENY:PIPE_NAME_IDENTITY";
        return null;
    }

    internal static string Open(string name, string attempt,
                                out SafeFileHandle retained)
    {
        retained = null;
        string denial = NameDenial(name);
        if (denial != null) return denial;
        uint access;
        try { access = Ea4eProtectedPipeAccessProbePolicy.RequestedAccess(attempt); }
        catch (ArgumentException) { return "DENY:UNKNOWN_ATTEMPT"; }

        SafeFileHandle opened = CreateFile(name, access, 0, IntPtr.Zero,
            OpenExisting, 0, IntPtr.Zero);
        if (opened == null || opened.IsInvalid)
        {
            int error = Marshal.GetLastWin32Error();
            if (opened != null) opened.Dispose();
            return Ea4eProtectedPipeAccessProbePolicy.Classify(
                attempt, false, error);
        }
        if (attempt != Ea4eProtectedPipeAccessProbePolicy.SpecificWrite)
        {
            opened.Dispose();
            return "DENY:UNEXPECTED_OPEN";
        }
        retained = opened;
        return "CANDIDATE:WRITE_HANDLE_ONLY";
    }
}
