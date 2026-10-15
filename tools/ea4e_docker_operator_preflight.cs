// Candidate for a separately reviewed protected installation. Not an issuer.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.RegularExpressions;

internal static class Program
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

    private static int Main(string[] args)
    {
        if (args.Length != 1 || !SidPattern.IsMatch(args[0]))
        {
            Console.WriteLine("DENY:EXPECTED_OPERATOR_SID_INVALID");
            return 1;
        }
        try
        {
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
            {
                if (identity.User == null || !String.Equals(
                    identity.User.Value, args[0], StringComparison.Ordinal))
                {
                    Console.WriteLine("DENY:OPERATOR_SID_MISMATCH");
                    return 1;
                }
            }
            if (!IsElevated())
            {
                Console.WriteLine("DENY:OPERATOR_TOKEN_NOT_ELEVATED");
                return 1;
            }
            Console.WriteLine("MATCH:EXPECTED_ELEVATED_TOKEN_OBSERVED");
            return 0;
        }
        catch (Exception)
        {
            Console.WriteLine("DENY:WINDOWS_TOKEN_UNAVAILABLE");
            return 1;
        }
    }
}
