using System;

internal static class Probe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1)
            return 2;
        try
        {
            using (var db = new Ea4eProtectedSqlite(args[0]))
            {
                db.Execute("CREATE TABLE sample (value TEXT NOT NULL)");
                db.Execute("BEGIN IMMEDIATE");
                using (var insert = db.Prepare("INSERT INTO sample(value) VALUES (?)"))
                {
                    insert.BindText(1, "quote ' and Unicode \u96ea");
                    if (insert.Step())
                        return 3;
                }
                db.Execute("COMMIT");
                db.Execute("BEGIN IMMEDIATE");
                db.Execute("INSERT INTO sample(value) VALUES ('rollback')");
                db.Execute("ROLLBACK");
            }
            using (var db = new Ea4eProtectedSqlite(args[0]))
            {
                using (var read = db.Prepare("SELECT value FROM sample"))
                {
                    if (!read.Step() || read.Text(0) != "quote ' and Unicode \u96ea"
                        || read.Step())
                        return 4;
                }
            }
            Console.WriteLine("REOPEN_COMMIT_ROLLBACK_PASS");
            return 0;
        }
        catch (Exception exception)
        {
            Console.WriteLine(exception.GetType().Name + ":" + exception.Message);
            return 1;
        }
    }
}
