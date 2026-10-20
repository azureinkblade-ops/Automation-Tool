// Source-only classification; native access and token identity need separate proof.
using System;

internal static class Ea4eProtectedPipeAccessProbePolicy
{
    internal const string SpecificWrite = "SPECIFIC_WRITE";
    internal const string GenericWrite = "GENERIC_WRITE";
    internal const string WriteDac = "WRITE_DAC";
    internal const string WriteOwner = "WRITE_OWNER";

    internal static uint RequestedAccess(string attempt)
    {
        switch (attempt)
        {
            case SpecificWrite: return 0x00000002;
            case GenericWrite: return 0x40000000;
            case WriteDac: return 0x00040000;
            case WriteOwner: return 0x00080000;
            default: throw new ArgumentException("Unknown access attempt", "attempt");
        }
    }

    internal static string Classify(string attempt, bool opened, int error)
    {
        try { RequestedAccess(attempt); }
        catch (ArgumentException) { return "DENY:UNKNOWN_ATTEMPT"; }
        if (opened)
            return attempt == SpecificWrite
                ? "CANDIDATE:WRITE_HANDLE_ONLY" : "DENY:UNEXPECTED_OPEN";
        if (error == 5)
            return attempt == SpecificWrite
                ? "DENY:SPECIFIC_WRITE_ACCESS" : "OBSERVED:ACCESS_DENIED_ONLY";
        if (error == 231) return "DENY:PIPE_BUSY_NOT_ACL";
        if (error == 2 || error == 3) return "DENY:PIPE_MISSING_NOT_ACL";
        return "DENY:OTHER_OPEN_ERROR";
    }
}
