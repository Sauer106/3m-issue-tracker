-- 3M Issues & Projects Tracker database schema
-- Run this in SSMS (or sqlcmd) on the SQL Server instance on your automation box.

IF DB_ID('IssueTracker') IS NULL
    CREATE DATABASE IssueTracker;
GO

USE IssueTracker;
GO

IF OBJECT_ID('dbo.Users') IS NULL
BEGIN
    CREATE TABLE dbo.Users (
        Id           INT IDENTITY(1,1) PRIMARY KEY,
        Username     NVARCHAR(50)  NOT NULL UNIQUE,
        DisplayName  NVARCHAR(100) NOT NULL,
        Email        NVARCHAR(255) NOT NULL,
        PasswordHash NVARCHAR(200) NOT NULL,
        IsAdmin      BIT NOT NULL DEFAULT 0,
        IsActive     BIT NOT NULL DEFAULT 1,
        MustChangePassword BIT NOT NULL DEFAULT 0,
        TotpSecret   NVARCHAR(64) NULL,   -- base32 TOTP seed; NULL = 2FA not yet enrolled
        FailedLogins INT NOT NULL DEFAULT 0,
        LockedUntil  DATETIME2 NULL,      -- lockout after repeated failed logins
        CreatedAt    DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

IF OBJECT_ID('dbo.Issues') IS NULL
BEGIN
    CREATE TABLE dbo.Issues (
        Id          INT IDENTITY(1,1) PRIMARY KEY,
        Title       NVARCHAR(200) NOT NULL,
        Description NVARCHAR(MAX) NOT NULL,
        Status      NVARCHAR(20)  NOT NULL DEFAULT 'Open', -- Open / In Progress / Waiting on Solventum / Hold / Closed
        IsMajor     BIT NOT NULL DEFAULT 0,
        SolventumTicket   NVARCHAR(50) NULL,
        ServiceDeskTicket NVARCHAR(50) NULL,
        Regions      NVARCHAR(MAX) NULL,  -- JSON list of region names
        Facilities   NVARCHAR(MAX) NULL,  -- JSON list of facility names
        ReportedBy  INT NOT NULL REFERENCES dbo.Users(Id),
        AssignedTo  INT NULL     REFERENCES dbo.Users(Id),
        CreatedAt   DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        UpdatedAt   DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        ResolvedAt  DATETIME2 NULL
    );
    CREATE INDEX IX_Issues_Status ON dbo.Issues(Status);
END
GO

IF OBJECT_ID('dbo.IssueUpdates') IS NULL
BEGIN
    CREATE TABLE dbo.IssueUpdates (
        Id           INT IDENTITY(1,1) PRIMARY KEY,
        IssueId      INT NOT NULL REFERENCES dbo.Issues(Id),
        AuthorId     INT NOT NULL REFERENCES dbo.Users(Id),
        Comment      NVARCHAR(MAX) NOT NULL,
        StatusChange NVARCHAR(50) NULL,   -- e.g. 'Open -> In Progress' when the update changed status
        FieldChanges NVARCHAR(MAX) NULL,  -- JSON list of {field, old, new} edits saved with this update
        IsFixProposal BIT NOT NULL DEFAULT 0,
        ProposalStatus NVARCHAR(10) NULL, -- Pending / Accepted / Declined (fix proposals only)
        CreatedAt    DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE INDEX IX_IssueUpdates_IssueId_CreatedAt ON dbo.IssueUpdates(IssueId, CreatedAt);
END
GO

IF OBJECT_ID('dbo.EmailLog') IS NULL
BEGIN
    CREATE TABLE dbo.EmailLog (
        Id        INT IDENTITY(1,1) PRIMARY KEY,
        EmailType NVARCHAR(20) NOT NULL,   -- 'reminder' or 'digest'
        IssueId   INT NULL,
        Recipient NVARCHAR(255) NOT NULL,
        SentAt    DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

IF OBJECT_ID('dbo.Projects') IS NULL
BEGIN
    CREATE TABLE dbo.Projects (
        Id                INT IDENTITY(1,1) PRIMARY KEY,
        Title             NVARCHAR(200) NOT NULL,
        Summary           NVARCHAR(MAX) NOT NULL,
        Status            NVARCHAR(20)  NOT NULL DEFAULT 'Planned', -- Planned / In Progress / On Hold / Completed / Cancelled
        SolventumTicket   NVARCHAR(50) NULL,
        ServiceDeskTicket NVARCHAR(50) NULL,
        Regions           NVARCHAR(MAX) NULL,  -- JSON list of region names
        Facilities        NVARCHAR(MAX) NULL,  -- JSON list of facility names
        CreatedBy         INT NOT NULL REFERENCES dbo.Users(Id),
        AssignedTo        INT NULL     REFERENCES dbo.Users(Id),
        CreatedAt         DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE INDEX IX_Projects_Status ON dbo.Projects(Status);
END
GO

IF OBJECT_ID('dbo.ProjectUpdates') IS NULL
BEGIN
    CREATE TABLE dbo.ProjectUpdates (
        Id           INT IDENTITY(1,1) PRIMARY KEY,
        ProjectId    INT NOT NULL REFERENCES dbo.Projects(Id),
        AuthorId     INT NOT NULL REFERENCES dbo.Users(Id),
        Comment      NVARCHAR(MAX) NOT NULL,
        StatusChange NVARCHAR(50) NULL,
        FieldChanges NVARCHAR(MAX) NULL,  -- JSON list of {field, old, new} edits saved with this update
        CreatedAt    DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE INDEX IX_ProjectUpdates_ProjectId_CreatedAt ON dbo.ProjectUpdates(ProjectId, CreatedAt);
END
GO

IF OBJECT_ID('dbo.AuditLog') IS NULL
BEGIN
    CREATE TABLE dbo.AuditLog (
        Id        INT IDENTITY(1,1) PRIMARY KEY,
        ActorId   INT NULL REFERENCES dbo.Users(Id),  -- who did it (NULL if the actor was later deleted)
        Action    NVARCHAR(60) NOT NULL,              -- e.g. 'delete_issue', 'reset_2fa'
        Detail    NVARCHAR(400) NULL,                 -- human-readable specifics
        CreatedAt DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE INDEX IX_AuditLog_CreatedAt ON dbo.AuditLog(CreatedAt DESC);
END
GO

IF OBJECT_ID('dbo.ExtraRecipients') IS NULL
BEGIN
    CREATE TABLE dbo.ExtraRecipients (
        Id    INT IDENTITY(1,1) PRIMARY KEY,
        Email NVARCHAR(255) NOT NULL,
        Label NVARCHAR(100) NULL   -- e.g. "HIM Manager", "3M distribution list"
    );
END
GO

IF OBJECT_ID('dbo.Presence') IS NULL
BEGIN
    CREATE TABLE dbo.Presence (
        UserId    INT NOT NULL,
        PageKey   NVARCHAR(50) NOT NULL,   -- e.g. 'issue:42' / 'project:7'
        FirstSeen DATETIME2 NOT NULL DEFAULT SYSDATETIME(),  -- earliest active viewer holds the edit lock
        LastSeen  DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        LastActivity DATETIME2 NOT NULL DEFAULT SYSDATETIME(),  -- last real interaction; idle holders lose the lock
        PRIMARY KEY (UserId, PageKey)
    );
END
GO

IF OBJECT_ID('dbo.Attachments') IS NULL
BEGIN
    CREATE TABLE dbo.Attachments (
        Id          INT IDENTITY(1,1) PRIMARY KEY,
        ParentType  NVARCHAR(10) NOT NULL,   -- 'issue' | 'project'
        ParentId    INT NOT NULL,
        FileName    NVARCHAR(255) NOT NULL,
        ContentType NVARCHAR(100) NULL,
        Content     VARBINARY(MAX) NOT NULL,
        UploadedBy  INT NOT NULL REFERENCES dbo.Users(Id),
        CreatedAt   DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE INDEX IX_Attachments_Parent ON dbo.Attachments(ParentType, ParentId);
END
GO

IF OBJECT_ID('dbo.Regions') IS NULL
BEGIN
    CREATE TABLE dbo.Regions (
        Id        INT IDENTITY(1,1) PRIMARY KEY,
        Name      NVARCHAR(100) NOT NULL UNIQUE,
        SortOrder INT NOT NULL DEFAULT 0
    );
END
GO

IF OBJECT_ID('dbo.Facilities') IS NULL
BEGIN
    CREATE TABLE dbo.Facilities (
        Id        INT IDENTITY(1,1) PRIMARY KEY,
        RegionId  INT NOT NULL REFERENCES dbo.Regions(Id) ON DELETE CASCADE,
        Name      NVARCHAR(100) NOT NULL,
        Code      NVARCHAR(20) NULL,
        SortOrder INT NOT NULL DEFAULT 0
    );
END
GO

-- Seed the initial region/facility list only on an empty table; after that the
-- list is managed from the app's Admin page.
IF NOT EXISTS (SELECT 1 FROM dbo.Regions)
BEGIN
    INSERT INTO dbo.Regions (Name, SortOrder) VALUES
        (N'Atlantic - Revenue Cycle', 1), (N'Atlantic', 2), (N'South Texas', 3),
        (N'Vegas', 4), (N'Pacific', 5);
    INSERT INTO dbo.Facilities (RegionId, Name, Code, SortOrder)
    SELECT r.Id, f.Name, f.Code, f.SortOrder
    FROM (VALUES
        (N'Atlantic - Revenue Cycle', N'Aiken', N'AIK', 1),
        (N'Atlantic', N'George Washington', N'CPG', 1),
        (N'Atlantic', N'Cedar Hill', N'CHR/CPZ', 2),
        (N'Atlantic', N'Manatee', N'MPZ', 3),
        (N'Atlantic', N'Lakewood Ranch', N'LPZ', 4),
        (N'Atlantic', N'Wellington', N'WPG', 5),
        (N'Atlantic', N'Alan B. Miller', N'MPG', 6),
        (N'South Texas', N'Texoma', N'APD', 1),
        (N'South Texas', N'Doctor''s Hospital of Laredo', N'SPH', 2),
        (N'South Texas', N'Northwest Texas', N'NPH', 3),
        (N'South Texas', N'Fort Duncan', N'FPH', 4),
        (N'South Texas', N'South Texas', N'MPF', 5),
        (N'South Texas', N'TMC - Bonham', N'CPH', 6),
        (N'South Texas', N'St. Mary''s', N'TPD', 7),
        (N'Vegas', N'Northern Nevada', N'SPE', 1),
        (N'Vegas', N'Sierra', N'SPE', 2),
        (N'Vegas', N'VHS - Centennial Hills', N'CGI', 3),
        (N'Vegas', N'VHS - Henderson', N'HGI', 4),
        (N'Vegas', N'VHS - Spring Valley', N'BGI', 5),
        (N'Vegas', N'VHS - Summerlin', N'UPE', 6),
        (N'Vegas', N'VHS - Valley', N'VPI', 7),
        (N'Vegas', N'VHS - West Henderson', N'WHH/WGI', 8),
        (N'Vegas', N'Desert View', N'DPI', 9),
        (N'Pacific', N'Temecula', N'TPI', 1),
        (N'Pacific', N'Southwest (Inland and Rancho)', N'NPI', 2),
        (N'Pacific', N'Corona', N'PSL', 3),
        (N'Pacific', N'Palmdale', N'LPI', 4)
    ) AS f(RegionName, Name, Code, SortOrder)
    JOIN dbo.Regions r ON r.Name = f.RegionName;
END
GO

-- Upgrade: issues and projects are scoped to regions/facilities (JSON lists).
IF COL_LENGTH('dbo.Issues', 'Regions') IS NULL
    ALTER TABLE dbo.Issues ADD Regions NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.Issues', 'Facilities') IS NULL
    ALTER TABLE dbo.Issues ADD Facilities NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.Projects', 'Regions') IS NULL
    ALTER TABLE dbo.Projects ADD Regions NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.Projects', 'Facilities') IS NULL
    ALTER TABLE dbo.Projects ADD Facilities NVARCHAR(MAX) NULL;
GO

-- Upgrade: presence rows track first-seen for the edit lock.
IF COL_LENGTH('dbo.Presence', 'FirstSeen') IS NULL
    ALTER TABLE dbo.Presence ADD FirstSeen DATETIME2 NOT NULL CONSTRAINT DF_Presence_FirstSeen DEFAULT SYSDATETIME();
GO
IF COL_LENGTH('dbo.Presence', 'LastActivity') IS NULL
    ALTER TABLE dbo.Presence ADD LastActivity DATETIME2 NOT NULL CONSTRAINT DF_Presence_LastActivity DEFAULT SYSDATETIME();
GO

-- Upgrade: 'Resolved' status retired; issues are Open / In Progress / Closed.
UPDATE dbo.Issues SET Status = 'Closed' WHERE Status = 'Resolved';
GO

-- Upgrade: issues can be flagged Major, and updates can be fix proposals.
IF COL_LENGTH('dbo.Issues', 'IsMajor') IS NULL
    ALTER TABLE dbo.Issues ADD IsMajor BIT NOT NULL CONSTRAINT DF_Issues_IsMajor DEFAULT 0;
GO
IF COL_LENGTH('dbo.IssueUpdates', 'IsFixProposal') IS NULL
    ALTER TABLE dbo.IssueUpdates ADD IsFixProposal BIT NOT NULL CONSTRAINT DF_IssueUpdates_IsFixProposal DEFAULT 0;
GO
IF COL_LENGTH('dbo.IssueUpdates', 'ProposalStatus') IS NULL
    ALTER TABLE dbo.IssueUpdates ADD ProposalStatus NVARCHAR(10) NULL;
GO
UPDATE dbo.IssueUpdates SET ProposalStatus = 'Pending' WHERE IsFixProposal = 1 AND ProposalStatus IS NULL;
GO

-- Upgrade: updates carry a JSON audit of field edits (who changed tickets/assignee/etc).
IF COL_LENGTH('dbo.IssueUpdates', 'FieldChanges') IS NULL
    ALTER TABLE dbo.IssueUpdates ADD FieldChanges NVARCHAR(MAX) NULL;
GO
IF COL_LENGTH('dbo.ProjectUpdates', 'FieldChanges') IS NULL
    ALTER TABLE dbo.ProjectUpdates ADD FieldChanges NVARCHAR(MAX) NULL;
GO

-- Upgrade for databases created before the forced-password-change feature.
IF COL_LENGTH('dbo.Users', 'MustChangePassword') IS NULL
    ALTER TABLE dbo.Users ADD MustChangePassword BIT NOT NULL DEFAULT 0;
GO

-- Upgrade: issues track vendor ticket numbers instead of category/priority.
IF COL_LENGTH('dbo.Issues', 'SolventumTicket') IS NULL
    ALTER TABLE dbo.Issues ADD SolventumTicket NVARCHAR(50) NULL;
GO
IF COL_LENGTH('dbo.Issues', 'ServiceDeskTicket') IS NULL
    ALTER TABLE dbo.Issues ADD ServiceDeskTicket NVARCHAR(50) NULL;
GO
IF COL_LENGTH('dbo.Issues', 'Category') IS NOT NULL
    ALTER TABLE dbo.Issues DROP COLUMN Category;
GO
IF COL_LENGTH('dbo.Issues', 'Priority') IS NOT NULL
    ALTER TABLE dbo.Issues DROP COLUMN Priority;
GO

-- Upgrade for databases created before the 2FA feature.
IF COL_LENGTH('dbo.Users', 'TotpSecret') IS NULL
    ALTER TABLE dbo.Users ADD TotpSecret NVARCHAR(64) NULL;
GO

-- Upgrade: per-user email preferences (managed from the Admin page).
IF COL_LENGTH('dbo.Users', 'ReceivesDigest') IS NULL
    ALTER TABLE dbo.Users ADD ReceivesDigest BIT NOT NULL CONSTRAINT DF_Users_ReceivesDigest DEFAULT 1;
GO
IF COL_LENGTH('dbo.Users', 'ReceivesReminders') IS NULL
    ALTER TABLE dbo.Users ADD ReceivesReminders BIT NOT NULL CONSTRAINT DF_Users_ReceivesReminders DEFAULT 1;
GO

-- Upgrade: brute-force lockout tracking.
IF COL_LENGTH('dbo.Users', 'FailedLogins') IS NULL
    ALTER TABLE dbo.Users ADD FailedLogins INT NOT NULL CONSTRAINT DF_Users_FailedLogins DEFAULT 0;
GO
IF COL_LENGTH('dbo.Users', 'LockedUntil') IS NULL
    ALTER TABLE dbo.Users ADD LockedUntil DATETIME2 NULL;
GO

-- The app and email scripts run as SYSTEM via Task Scheduler; grant it access.
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'NT AUTHORITY\SYSTEM')
    CREATE LOGIN [NT AUTHORITY\SYSTEM] FROM WINDOWS;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'NT AUTHORITY\SYSTEM')
    CREATE USER [NT AUTHORITY\SYSTEM] FOR LOGIN [NT AUTHORITY\SYSTEM];
GO

ALTER ROLE db_datareader ADD MEMBER [NT AUTHORITY\SYSTEM];
ALTER ROLE db_datawriter ADD MEMBER [NT AUTHORITY\SYSTEM];
ALTER ROLE db_backupoperator ADD MEMBER [NT AUTHORITY\SYSTEM];  -- nightly backup task runs as SYSTEM
GO
