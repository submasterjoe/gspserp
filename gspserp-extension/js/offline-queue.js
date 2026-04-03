/**
 * IndexedDB-backed offline request queue (max 100 items).
 */
(function () {
  const DB_NAME = "gspserp_offline_v1";
  const STORE = "requests";
  const MAX = 100;
  const DB_VERSION = 1;

  /**
   * @returns {Promise<IDBDatabase>}
   */
  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * @param {{ type: string, payload: object, retries?: number }} item
   */
  async function enqueue(item) {
    const db = await openDb();
    const count = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const st = tx.objectStore(STORE);
      const r = st.count();
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
    if (count >= MAX) {
      db.close();
      throw new Error("Offline queue is full (100 items).");
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const rec = {
        type: item.type,
        payload: item.payload,
        retries: item.retries || 0,
        createdAt: Date.now(),
      };
      tx.objectStore(STORE).add(rec);
      tx.oncomplete = () => {
        db.close();
        resolve(true);
      };
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * @returns {Promise<Array<{ id: number } & object>>}
   */
  async function listAll() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const st = tx.objectStore(STORE);
      const r = st.getAll();
      r.onsuccess = () => {
        db.close();
        resolve(r.result || []);
      };
      r.onerror = () => reject(r.error);
    });
  }

  /**
   * @param {number} id
   */
  async function remove(id) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * @returns {Promise<number>}
   */
  async function size() {
    const all = await listAll();
    return all.length;
  }

  globalThis.GspsOfflineQueue = {
    enqueue,
    listAll,
    remove,
    size,
    MAX,
  };
})();
