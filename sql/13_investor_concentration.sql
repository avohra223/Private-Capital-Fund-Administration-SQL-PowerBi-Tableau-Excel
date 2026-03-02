-- Query 13: Investor Concentration Risk
-- Business question: What percentage of total AUM does each LP represent?
-- High concentration in one LP = risk if they withdraw or default

WITH Total_AUM AS (
    SELECT SUM(Commitment_Amount) AS Grand_Total
    FROM Commitments
),
Investor_Commitments AS (
    SELECT 
        Investor_ID,
        SUM(Commitment_Amount) AS Investor_Total
    FROM Commitments
    GROUP BY Investor_ID
)
SELECT
    Investors.Investor_Name,
    Investors.Investor_Type,
    Investors.Country,
    Investor_Commitments.Investor_Total,
    Total_AUM.Grand_Total,
    ROUND(Investor_Commitments.Investor_Total * 100.0 / Total_AUM.Grand_Total, 2) AS Pct_Of_Total_AUM
FROM Investors
JOIN Investor_Commitments ON Investors.Investor_ID = Investor_Commitments.Investor_ID
CROSS JOIN Total_AUM
ORDER BY Pct_Of_Total_AUM DESC;
