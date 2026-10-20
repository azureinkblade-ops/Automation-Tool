// Inert mask policy only; no file is opened by this candidate.
using System;

internal static class Ea4eAnnouncementSharePolicyCandidate
{
    private const uint FileReadData = 0x00000001;
    private const uint FileWriteData = 0x00000002;
    private const uint FileReadAttributes = 0x00000080;
    private const uint ReadControl = 0x00020000;
    private const uint AccessSystemSecurity = 0x01000000;
    private const uint FileShareRead = 0x00000001;
    private const uint FileShareWrite = 0x00000002;
    private const uint FileShareDelete = 0x00000004;

    internal static uint CreatorDesiredAccess()
    {
        return FileWriteData | ReadControl | AccessSystemSecurity;
    }
    internal static uint CreatorShareMode() { return FileShareRead; }
    internal static uint ReaderDesiredAccess()
    {
        return FileReadData | FileReadAttributes | ReadControl;
    }
    internal static uint ReaderShareMode()
    {
        return FileShareRead | FileShareWrite;
    }

    internal static string Screen(uint creatorAccess, uint creatorShare,
                                  uint readerAccess, uint readerShare)
    {
        if (creatorAccess != CreatorDesiredAccess() ||
            creatorShare != CreatorShareMode() ||
            readerAccess != ReaderDesiredAccess() ||
            readerShare != ReaderShareMode() ||
            (creatorShare & FileShareDelete) != 0 ||
            (readerShare & FileShareDelete) != 0 ||
            (creatorShare & FileShareRead) == 0 ||
            (readerShare & FileShareWrite) == 0)
            return "DENY:ANNOUNCEMENT_SHARE_POLICY";
        return "CANDIDATE:SHARE_MASKS_ONLY";
    }
}
