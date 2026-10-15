// Candidate for a separately reviewed protected installation. Not an issuer.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.RegularExpressions;

internal static class Ea4eOperatorTokenObservation
{
    private const uint TokenQuery = 0x0008;
    private const int TokenElevation = 20;
    private static readonly Regex SidPattern = new Regex(
        @"\AS-[0-9]+(?:-[0-9]+){2,}\z", RegexOptions.CultureInvariant);

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(
        IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(
        IntPtr tokenHandle, int tokenInformationClass, out uint tokenInformation,
        uint tokenInformationLength, out uint returnLength);

    private static bool IsElevated()
    {
        IntPtr token;
        if (!OpenProcessToken(GetCurrentProcess(), TokenQuery, out token))
            throw new InvalidOperationException("Token open failed");
        try
        {
            uint elevated;
            uint returned;
            if (!GetTokenInformation(
                token, TokenElevation, out elevated, sizeof(uint), out returned)
                || returned != sizeof(uint) || elevated > 1)
                throw new InvalidOperationException("Token elevation query failed");
            return elevated == 1;
        }
        finally
        {
            if (!CloseHandle(token))
                throw new InvalidOperationException("Token close failed");
        }
    }

    internal static string Denial(string expectedSid)
    {
        if (String.IsNullOrEmpty(expectedSid) || !SidPattern.IsMatch(expectedSid))
            return "EXPECTED_OPERATOR_SID_INVALID";
        try
        {
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
            {
                if (identity.User == null || !String.Equals(
                    identity.User.Value, expectedSid, StringComparison.Ordinal))
                    return "OPERATOR_SID_MISMATCH";
            }
            if (!IsElevated())
                return "OPERATOR_TOKEN_NOT_ELEVATED";
            return null;
        }
        catch (Exception)
        {
            return "WINDOWS_TOKEN_UNAVAILABLE";
        }
    }
}

internal static class Program
{
    private static int Main(string[] args)
    {
        string denial = Ea4eOperatorTokenObservation.Denial(
            args.Length == 1 ? args[0] : null);
        Console.WriteLine(denial == null
            ? "MATCH:EXPECTED_ELEVATED_TOKEN_OBSERVED" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}
