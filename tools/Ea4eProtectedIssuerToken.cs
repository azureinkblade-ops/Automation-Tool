// Read-only Windows token witness for a future separately installed issuer.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.RegularExpressions;

internal static class Ea4eProtectedIssuerToken
{
    private const int TokenElevation = 20;
    private static readonly Regex Sid = new Regex(@"\AS-[0-9]+(?:-[0-9]+){2,}\z");

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool GetTokenInformation(
        IntPtr token, int informationClass, out int information,
        int informationLength, out int returnedLength);

    internal sealed class Observation
    {
        internal readonly string AccountSid;
        internal readonly bool Elevated;

        internal Observation(string accountSid, bool elevated)
        {
            AccountSid = accountSid;
            Elevated = elevated;
        }
    }

    internal static Observation ReadCurrent()
    {
        using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
        {
            if (identity == null || identity.User == null)
                throw new InvalidOperationException("Token user unavailable");
            int elevation, returned;
            if (!GetTokenInformation(identity.Token, TokenElevation, out elevation,
                                     sizeof(int), out returned)
                || returned != sizeof(int) || (elevation != 0 && elevation != 1))
                throw new InvalidOperationException("Token elevation unavailable");
            string sid = identity.User.Value;
            if (sid == null || !Sid.IsMatch(sid))
                throw new InvalidOperationException("Token SID malformed");
            return new Observation(sid, elevation == 1);
        }
    }

    internal static string Evaluate(string expectedSid, Observation observed)
    {
        if (expectedSid == null || !Sid.IsMatch(expectedSid))
            return "EXPECTED_SID_INVALID";
        if (observed == null || observed.AccountSid == null
            || !Sid.IsMatch(observed.AccountSid))
            return "TOKEN_OBSERVATION_INVALID";
        if (!String.Equals(expectedSid, observed.AccountSid, StringComparison.Ordinal))
            return "TOKEN_SID_MISMATCH";
        return observed.Elevated ? "MATCH_ELEVATED_TOKEN" : "TOKEN_NOT_ELEVATED";
    }
}
