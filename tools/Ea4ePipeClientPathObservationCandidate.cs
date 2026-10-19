// Read-only pipe client and protected-path observation; not an issuer.
using System;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientPathObservationCandidate
{
    internal static string Denial(
        SafePipeHandle pipe, IntPtr expectedProcess, string expectedAppSid,
        string path, string protectedRoot, string expectedSha256)
    {
        string process = Ea4ePipeClientProcessCandidate.Denial(
            pipe, expectedProcess);
        if (process != null) return process;

        string observation = Ea4ePipeClientTokenCandidate.DenialWithToken(
            pipe, expectedAppSid,
            token => Ea4eProtectedPathAccessCandidate.DenialWithBoundClientToken(
                path, protectedRoot, expectedAppSid, expectedSha256, token));
        if (observation != null) return observation;

        return Ea4ePipeClientProcessCandidate.Denial(pipe, expectedProcess);
    }
}
