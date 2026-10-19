// Read-only pipe client and protected-path observation; not an issuer.
using System;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientPathObservationCandidate
{
    internal static string DenialForExpectedKernelClient(
        SafePipeHandle pipe, uint expectedProcessId, long expectedCreationTime,
        string expectedAppSid, string path, string protectedRoot,
        string expectedSha256)
    {
        if (expectedProcessId == 0 || expectedCreationTime <= 0)
            return "EXPECTED_APP_PROCESS_INVALID";
        return Ea4ePipeClientProcessLeaseCandidate.Denial(
            pipe, (process, processId, creationTime) =>
            {
                if (processId != expectedProcessId
                    || creationTime != expectedCreationTime)
                    return "APP_PROCESS_IDENTITY_MISMATCH";
                return Denial(pipe, process, expectedAppSid, path,
                              protectedRoot, expectedSha256);
            });
    }

    internal static string DenialForKernelClient(
        SafePipeHandle pipe, string expectedAppSid, string path,
        string protectedRoot, string expectedSha256)
    {
        return Ea4ePipeClientProcessLeaseCandidate.Denial(
            pipe, (process, processId, creationTime) =>
                Denial(pipe, process, expectedAppSid, path,
                       protectedRoot, expectedSha256));
    }

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
