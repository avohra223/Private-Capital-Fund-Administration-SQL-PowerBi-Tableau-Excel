-- Query 14: Unfunded Commitments by Investor
-- Business question: How much capital is each LP still obligated to contribute?
-- This drives future cash flow planning for the fund

WITH Called AS (
    SELECT Investor_ID, SUM(Amount_Fund_Base) AS Total_Called
    FROM Transactions
    WHERE Txn_Type = 'Capital Call'
    GROUP BY Investor_ID
)
SELECT
    Investors.Investor_Name,
    Investors.Investor_Type,
    Investors.Country,
    SUM(Commitments.Commitment_Amount) AS Total_Committed,
    COALESCE(Called.Total_Called, 0) AS Total_Called,
    SUM(Commitments.Commitment_Amount) - COALESCE(Called.Total_Called, 0) AS Unfunded_Commitment,
    ROUND((SUM(Commitments.Commitment_Amount) - COALESCE(Called.Total_Called, 0)) * 100.0 / 
        SUM(Commitments.Commitment_Amount), 2) AS Pct_Unfunded
FROM Investors
JOIN Commitments ON Investors.Investor_ID = Commitments.Investor_ID
LEFT JOIN Called ON Investors.Investor_ID = Called.Investor_ID
GROUP BY Investors.Investor_Name, Investors.Investor_Type, Investors.Country, Called.Total_Called
ORDER BY Unfunded_Commitment DESC;
