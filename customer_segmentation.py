import sqlite3
import json
import pandas as pd
import numpy as np
import pickle
import os
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA

DB = "superstore.db"
CLUSTER_CSV = "customer_clusters.csv"
MODEL_PKL = "kmeans_model.pkl"
SCALER_PKL = "scaler.pkl"
METRICS_JSON = "cluster_metrics.json"
CLUSTER_CENTERS_CSV = "cluster_centers.csv"
PCA_CSV = "cluster_pca.csv"

CLUSTER_NAMES = {
    1: "Regular Customers",
    0: "Medium Value Customers",
    2: "VIP Customers",
    3: "Occasional Customers",
}


def compute_features(conn):
    customers = pd.read_sql_query("SELECT Customer_ID, Customer_Name, Segment FROM customers", conn)
    orders = pd.read_sql_query(
        "SELECT Order_ID, Customer_ID, Order_Date, Ship_Date FROM orders", conn,
        parse_dates=["Order_Date", "Ship_Date"]
    )
    order_details = pd.read_sql_query(
        "SELECT Order_ID, Product_ID, Sales FROM order_details", conn
    )

    sales_per_customer = order_details.merge(orders[["Order_ID", "Customer_ID"]], on="Order_ID")
    cust_agg = sales_per_customer.groupby("Customer_ID").agg(
        Customer_Total_Sales=("Sales", "sum"),
        Customer_Order_Count=("Order_ID", "nunique"),
    ).reset_index()
    cust_agg["Average_Order_Value"] = (
        cust_agg["Customer_Total_Sales"] / cust_agg["Customer_Order_Count"]
    ).round(2)

    date_range = (orders["Order_Date"].max() - orders["Order_Date"].min()).days / 365.25
    cust_agg["Purchase_Frequency"] = (
        cust_agg["Customer_Order_Count"] / date_range
    ).round(2)

    result = customers.merge(cust_agg, on="Customer_ID", how="left")
    return result


def run_kmeans(df):
    feature_cols = [
        "Customer_Total_Sales",
        "Customer_Order_Count",
        "Average_Order_Value",
        "Purchase_Frequency",
    ]
    X = df[feature_cols].fillna(0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=4, random_state=42)
    labels = kmeans.fit_predict(X_scaled)

    sil = round(silhouette_score(X_scaled, labels), 4)

    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)

    df["Cluster"] = labels
    df["Cluster_Name"] = df["Cluster"].map(CLUSTER_NAMES)
    df["PCA1"] = X_pca[:, 0]
    df["PCA2"] = X_pca[:, 1]
    return df, kmeans, scaler, sil


def save_artifacts(df, kmeans, scaler, sil):
    out = df[["Customer_ID", "Customer_Name", "Segment", "Cluster", "Cluster_Name",
              "Customer_Total_Sales", "Customer_Order_Count", "Average_Order_Value",
              "Purchase_Frequency", "PCA1", "PCA2"]]
    out.to_csv(CLUSTER_CSV, index=False)
    with open(MODEL_PKL, "wb") as f:
        pickle.dump(kmeans, f)
    with open(SCALER_PKL, "wb") as f:
        pickle.dump(scaler, f)

    with open(METRICS_JSON, "w") as f:
        json.dump({"silhouette_score": sil, "n_clusters": 4}, f)

    centers = scaler.inverse_transform(kmeans.cluster_centers_)
    cols = ["Customer_Total_Sales", "Customer_Order_Count", "Average_Order_Value", "Purchase_Frequency"]
    centers_df = pd.DataFrame(centers, columns=cols)
    centers_df["Cluster"] = range(4)
    centers_df["Cluster_Name"] = centers_df["Cluster"].map(CLUSTER_NAMES)
    centers_df.to_csv(CLUSTER_CENTERS_CSV, index=False)


def main():
    conn = sqlite3.connect(DB)
    df = compute_features(conn)
    conn.close()
    df, kmeans, scaler, sil = run_kmeans(df)
    save_artifacts(df, kmeans, scaler, sil)
    print(f"Clustered {len(df)} customers into {len(df['Cluster_Name'].unique())} segments")
    print(f"Silhouette score: {sil}")
    print(df["Cluster_Name"].value_counts().to_string())


if __name__ == "__main__":
    main()
