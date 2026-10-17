// Read-only composition of the pipe client process and token observations.
using System;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeClientBindingCandidate
{
    internal static string Denial(
        SafePipeHandle pipe, IntPtr expectedProcess, string expectedAppSid)
    {
        string process = Ea4ePipeClientProcessCandidate.Denial(
            pipe, expectedProcess);
        if (process != null)
            return process;

        string token = Ea4ePipeClientTokenCandidate.Denial(
            pipe, expectedAppSid);
        if (token != null)
            return token;

        return Ea4ePipeClientProcessCandidate.Denial(pipe, expectedProcess);
    }
}
