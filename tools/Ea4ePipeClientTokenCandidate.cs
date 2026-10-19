// Read-only client-token observation; not an issuer or operator witness.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientTokenCandidate
{
    private const uint TokenQuery = 0x0008;
    private const int TokenImpersonationLevel = 9;
    private const int TokenElevationType = 18;
    private const int TokenElevation = 20;
    private static readonly Regex SidPattern = new Regex(
        @"\AS-[0-9]+(?:-[0-9]+){2,}\z", RegexOptions.CultureInvariant);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ImpersonateNamedPipeClient(SafePipeHandle pipe);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool RevertToSelf();

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentThread();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenThreadToken(
        IntPtr thread, uint access, [MarshalAs(UnmanagedType.Bool)] bool openAsSelf,
        out SafeFileHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(
        SafeFileHandle token, int informationClass, out int information,
        uint length, out uint returned);

    private static bool TokenValue(SafeFileHandle token, int kind, out int value)
    {
        uint returned;
        return GetTokenInformation(token, kind, out value, sizeof(int), out returned)
            && returned == sizeof(int);
    }

    internal static string Denial(SafePipeHandle pipe, string expectedAppSid)
    {
        return DenialWithToken(pipe, expectedAppSid, token => null);
    }

    internal static string DenialWithToken(
        SafePipeHandle pipe, string expectedAppSid,
        Func<SafeFileHandle, string> observe)
    {
        if (String.IsNullOrEmpty(expectedAppSid) || !SidPattern.IsMatch(expectedAppSid))
            return "EXPECTED_APP_SID_INVALID";
        if (pipe == null || pipe.IsInvalid || pipe.IsClosed)
            return "PIPE_HANDLE_UNAVAILABLE";
        if (observe == null) return "CLIENT_OBSERVER_UNAVAILABLE";
        if (!ImpersonateNamedPipeClient(pipe))
            return "CLIENT_IMPERSONATION_FAILED";
        try
        {
            SafeFileHandle token;
            if (!OpenThreadToken(GetCurrentThread(), TokenQuery, true, out token))
                return "CLIENT_TOKEN_UNAVAILABLE";
            using (token)
            {
                int level;
                int elevationType;
                int elevated;
                if (!TokenValue(token, TokenImpersonationLevel, out level)
                    || level < 2
                    || !TokenValue(token, TokenElevationType, out elevationType)
                    || elevationType == 2
                    || !TokenValue(token, TokenElevation, out elevated)
                    || elevated != 0)
                    return "CLIENT_TOKEN_NOT_LIMITED";
                using (var identity = new WindowsIdentity(token.DangerousGetHandle()))
                    if (identity.User == null || !String.Equals(
                        identity.User.Value, expectedAppSid, StringComparison.Ordinal))
                        return "CLIENT_SID_MISMATCH";
                return observe(token);
            }
        }
        catch
        {
            return "CLIENT_TOKEN_OBSERVATION_FAILED";
        }
        finally
        {
            if (!RevertToSelf())
                Environment.FailFast("EA4E_PIPE_REVERT_FAILED");
        }
    }
}
