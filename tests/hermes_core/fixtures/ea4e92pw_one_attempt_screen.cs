using System;

internal static class Ea4e92pwOneAttemptScreen
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        const string sid = "S-1-5-21-1-2-3-1001";
        const string sddl = "O:BAG:BAD:P(A;;0x000200a1;;;" + sid +
            ")(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)";
        string result;
        if (args[0] == "valid")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
                sid, sddl, 0x012200a1, 3, 1);
        else if (args[0] == "share-delete")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
                sid, sddl, 0x012200a1, 7, 1);
        else if (args[0] == "missing-sid")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
                null, sddl, 0x012200a1, 3, 1);
        else return 2;
        Console.WriteLine(result ?? "CANDIDATE:INPUTS_ONLY");
        return 0;
    }
}
