import time
import pandas as pd
import numpy as np
from numpy.linalg import norm
import json

from interfaces.pgvector_interface import PGvectorInterface
from interfaces.milvus_interface import MilvusInterface
from interfaces.qdrant_interface import QDrantInterface


def get_data_info(csv_path):
    df = pd.read_csv(csv_path)
    df = df.to_numpy()
    return df.shape


test_db_interface = [QDrantInterface, MilvusInterface, PGvectorInterface]
test_db_interface = [PGvectorInterface]
test_metric = {
    PGvectorInterface: ["cosine", "l2"],
    MilvusInterface: ["COSINE", "L2"],
    QDrantInterface: ["Cosine", "L2"]
}
test_index_type = {
    PGvectorInterface: ["hnsw", "ivfflat"],
    MilvusInterface: ["HNSW", "FLAT"],
    QDrantInterface: ["HNSW"]
}
db_name_dict = {
    PGvectorInterface: "PGvector",
    MilvusInterface: "Milvus",
    QDrantInterface: "QDrant"
}


def benchmark_test(i, index_type: str, metric: str, db_BM,
                   db, collection_name, csv_path, test_vector):
    t_name = f"{index_type.upper()}+{metric.upper()}"
    if i == 0:
        db_BM["Methods"][t_name] = {}
        db_BM["Methods"][t_name]["create_time"] = 0
        db_BM["Methods"][t_name]["insert_time"] = 0
        db_BM["Methods"][t_name]["similarity_time"] = 0
        db_BM["Methods"][t_name]["size"] = 0
        db_BM["Methods"][t_name]["total_distance"] = 0
    print(f"Round {i+1} start")

    db.drop_table(collection_name)
    # print(index_type, metric)

    # create table
    start_time = time.time()
    db.create_table(collection_name, test_vector.shape[1], metric=metric,
                    index_types=index_type)
    db_BM["Methods"][t_name]["create_time"] += (time.time() -
                                                start_time)

    # prepare data
    data = db.transfer_csv(csv_path)
    # insert data
    start_time = time.time()
    db.insert_vector_from_csv(collection_name, data)
    if index_type == "ivfflat" or db_BM["Name"] == "Milvus":
        # if index_type == "ivfflat":
        #     pass
        print("indexing")
        db.indexing_data(collection_name, metric, index_type)
    db_BM["Methods"][t_name]["insert_time"] += (
        len(data) / (time.time() - start_time)
    )

    # size of table
    db_BM["Methods"][t_name]["size"] += db.get_size_of_table(
        collection_name
    )

    distances_total = 0
    # similarity_search
    start_time = time.time()
    for test_i in range(test_vector.shape[0]):
        id, _ = db.similarity_search(
            collection_name,
            test_vector[test_i, :],
            metric
        )
        # print(f"{dist = }")
        # print(data[id])
        B = test_vector[test_i, :]
        if db_BM["Name"] == "PGvector":
            A = data[id][1]
        elif db_BM["Name"] == "QDrant":
            A = data[id].vector
        else:
            A = data[id]["vector"]

        if metric.upper() == "COSINE":
            distances_total += np.dot(A, B)/(norm(A)*norm(B))
        else:
            distances_total += norm(A-B)
        # print(f"{npdist = }")

    db_BM["Methods"][t_name]["similarity_time"] += (
        test_vector.shape[0] / (time.time() - start_time)
    )

    db_BM["Methods"][t_name]["total_distance"] += (distances_total /
                                                   test_vector.shape[0])

    # others ...
    print(f"{distances_total = }")

    # print results

    return db_BM


def Benchmark(
    csv_path,
    test_csv_path,
    test_round=1,
    collection_name="vector_benchmark_test",
    result_file="./result/result.json",
    pg_dbname='postgres',
    pg_username='billyslim',
    pg_password='',
    milvus_db_path='milvus_db/milvus_demo.db',
    qdrant_db_path='./qdrant_data'
):
    train_data_shape = get_data_info(csv_path)
    test_data_shape = get_data_info(test_csv_path)
    test_vector = pd.read_csv(test_csv_path)
    test_vector = test_vector.to_numpy()
    db_benchmarks = []

    print("Start Benchmark process")
    print("#"*40)
    print("Informaton of dataset")
    assert train_data_shape[1] == test_data_shape[1]

    print(f"""Training dataset:
    # vector = {train_data_shape[0]}
    dimension = {train_data_shape[1]}""")
    print(f"""Testing dataset:
    # vector = {test_data_shape[0]}
    dimension = {test_data_shape[1]}""")

    test_interfaces = []
    if len(qdrant_db_path) > 0:
        test_interfaces.append(QDrantInterface)
        print("Added QDrantInterface to the test.")
    if len(milvus_db_path) > 0:
        test_interfaces.append(MilvusInterface)
        print("Added MilvusInterface to the test.")
    if len(pg_dbname) > 0 or len(pg_username) > 0:
        test_interfaces.append(PGvectorInterface)
        print("Added PGvectorInterface to the test.")

    total_start_time = time.time()

    for db_interface in test_interfaces:
        # print(db_name_dict[db_interface])
        if db_interface == PGvectorInterface:
            db = db_interface(pg_dbname, pg_username)
        elif db_interface == MilvusInterface:
            db = db_interface(milvus_db_path)
        elif db_interface == QDrantInterface:
            db = db_interface(qdrant_db_path)
        else:
            continue

        db_BM = {
            "Name": db_name_dict[db_interface],
            "Train-Data-info": {
                "#vector": train_data_shape[0],
                "dimension": train_data_shape[1]
            },
            "Test-Data-info": {
                "#vector": test_data_shape[0],
                "dimension": test_data_shape[1]
            },
            "Test round": test_round,
            "Methods": {}
        }

        for index_type in test_index_type[db_interface]:
            for metric in test_metric[db_interface]:
                print("#"*40)
                print(f"{db_name_dict[db_interface]}")
                print(f"{index_type = } and {metric = }")
                for i in range(test_round):
                    round_strat_time = time.time()
                    db_BM = benchmark_test(i, index_type, metric,
                                           db_BM, db, collection_name,
                                           csv_path, test_vector)
                    print(f"Round {i+1} spent {time.time()-round_strat_time}")
                t_name = f"{index_type.upper()}+{metric.upper()}"
                db_BM["Methods"][t_name]["create_time"] /= test_round
                db_BM["Methods"][t_name]["insert_time"] /= test_round
                db_BM["Methods"][t_name]["similarity_time"] /= test_round
                db_BM["Methods"][t_name]["size"] /= test_round
                db_BM["Methods"][t_name]["total_distance"] /= test_round

        db.drop_table(collection_name)
        db.disconnect_server()
        # print(db_BM)
        db_benchmarks.append(db_BM.copy())

    print("#"*40)
    print(f"Total process time: {time.time() - total_start_time}")

    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(db_benchmarks, f, ensure_ascii=False, indent=4)

    return 0


if __name__ == "__main__":
    csv_path = "./data/clustered_vectors_small.csv"
    test_csv_path = "./data/clustered_vectors_test_small.csv"
    result_file = "./result/result_small.json"
    # csv_path = "./data/clustered_vectors.csv"
    # test_csv_path = "./data/clustered_vectors_test.csv"
    # result_file = "./result/result.json"
    Benchmark(csv_path, test_csv_path, result_file=result_file, test_round=1)
