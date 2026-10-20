using System;

internal sealed class FakeHandle : IDisposable
{
    internal bool Closed;
    public void Dispose() { Closed = true; }
}

internal sealed class FakePort : IEa4eDirectoryFirstChildPort
{
    internal string Mode;
    internal int ParentCalls;
    internal int CreateCalls;
    internal int ScreenCalls;
    internal FakeHandle Handle;
    internal bool ExactArguments;

    public string ScreenParent(string path)
    {
        ParentCalls++;
        if (Mode == "parent") return "PARENT_MISMATCH";
        if (Mode == "throw-parent") throw new InvalidOperationException();
        return null;
    }

    public string Create(string path, string sddl, uint access, uint share,
                         uint flags, out IDisposable handle)
    {
        CreateCalls++;
        ExactArguments = path == @"C:\ProgramData\Hermes" &&
            sddl.Contains("0x000200a1") && access == 0x012200a1 &&
            share == 3 && flags == 1;
        Handle = new FakeHandle();
        handle = Handle;
        if (Mode == "collision") return "ALREADY_EXISTS";
        if (Mode == "missing-handle") { handle = null; return null; }
        if (Mode == "throw-create") throw new InvalidOperationException();
        return null;
    }

    public string ScreenCreated(IDisposable handle, string path, string sddl)
    {
        ScreenCalls++;
        if (Mode == "readback") return "DESCRIPTOR_MISMATCH";
        if (Mode == "throw-screen") throw new InvalidOperationException();
        return null;
    }
}

internal static class Ea4e92pjFirstChildFakeProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        var port = new FakePort { Mode = args[0] };
        string result = Ea4eDirectoryFirstChildCandidate.Attempt(
            @"C:\ProgramData",
            @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
            "S-1-5-21-100-200-300-1001", port);
        Console.WriteLine(result);
        Console.WriteLine(port.ParentCalls + ":" + port.CreateCalls + ":" +
                          port.ScreenCalls + ":" + port.ExactArguments + ":" +
                          (port.Handle != null && port.Handle.Closed));
        return 0;
    }
}
