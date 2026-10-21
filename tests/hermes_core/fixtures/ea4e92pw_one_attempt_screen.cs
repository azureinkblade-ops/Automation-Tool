using System;

internal static class Ea4e92pwOneAttemptScreen
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        const string sid = "S-1-5-21-1-2-3-1001";
        const string sddl = "O:BAG:BAD:P(A;;0x000200a1;;;" + sid +
            ")(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)";
        const string parent = @"C:\ProgramData";
        const string manifest = @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1";
        const string first = @"C:\ProgramData\Hermes";
        string result;
        if (args[0] == "valid")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, manifest, first, sid, sddl, 0x012200a1, 3, 1);
        else if (args[0] == "share-delete")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, manifest, first, sid, sddl, 0x012200a1, 7, 1);
        else if (args[0] == "missing-sid")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, manifest, first, null, sddl, 0x012200a1, 3, 1);
        else if (args[0] == "wrong-child")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, manifest, manifest, sid, sddl, 0x012200a1, 3, 1);
        else if (args[0] == "wrong-manifest")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, first, first, sid, sddl, 0x012200a1, 3, 1);
        else if (args[0] == "different-descriptor")
            result = Ea4eDirectory2OneAttemptCandidate.ScreenInputs(
                parent, manifest, first, sid,
                sddl.Replace("O:BA", "O:SY"), 0x012200a1, 3, 1);
        else if (args[0] == "pre-call")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyUncertain(false, false);
        else if (args[0] == "post-call")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyUncertain(true, false);
        else if (args[0] == "raw-close")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyUncertain(true, true);
        else if (args[0] == "wrapper-close-observed")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyRelease(true);
        else if (args[0] == "wrapper-close-unobserved")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyRelease(false);
        else if (args[0] == "pre-attempt-denial")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyDisposition(false, false);
        else if (args[0] == "post-attempt-denial")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyDisposition(true, false);
        else if (args[0] == "post-attempt-retained")
            result = Ea4eDirectory2OneAttemptCandidate.ClassifyDisposition(true, true);
        else return 2;
        Console.WriteLine(result ?? "CANDIDATE:INPUTS_ONLY");
        return 0;
    }
}
