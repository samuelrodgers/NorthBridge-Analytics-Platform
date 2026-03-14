-- This file contains all the queries for the frontend Superset charts. 
-- Each query was handwritten by Sam Rodgers and reviewed by Claude AI.



-- Main TX
-- Displays time-series data on total revenue per company
-- Will include lots of dropdown options that are not described in this query

-- There are issues with the database that need to be resolved before this chart can be made properly



-- Companies Tracked
-- Displays the number of companies with data in the system
-- Simple big number format, might add links later for quick navigation

SELECT COUNT(c_id) AS total_companies
FROM analytics.d_company;