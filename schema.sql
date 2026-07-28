-- 3M Issue Tracker database schema
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
        Category    NVARCHAR(50)  NOT NULL,
        Priority    NVARCHAR(20)  NOT NULL,              -- Low / Medium / High / Critical
        Status      NVARCHAR(20)  NOT NULL DEFAULT 'Open', -- Open / In Progress / Resolved / Closed
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
