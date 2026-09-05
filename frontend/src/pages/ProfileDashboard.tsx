import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useUser } from '../contexts/UserContext';
import { api } from '../api/client';
import { formatDate } from '../lib/datetime'

export default function ProfileDashboard() {
  const { profile, refetch } = useUser();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  // Fallback as date format
  const joinDate = profile?.createdAt ? formatDate(profile.createdAt, { month: 'long', year: 'numeric' }) : '2026';

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      setUploadError('Lütfen geçerli bir resim dosyası seçin.');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setUploadError('Dosya boyutu 5MB\'dan küçük olmalıdır.');
      return;
    }

    try {
      setIsUploading(true);
      setUploadError('');
      
      const formData = new FormData();
      formData.append('file', file);
      
      await api.postForm('/auth/profile-picture', formData);
      
      // Update profile picture URL globally
      await refetch();
    } catch (err) {
      console.error(err);
      setUploadError('Profil fotoğrafı yüklenirken bir hata oluştu.');
    } finally {
      setIsUploading(false);
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const getProfilePicture = () => {
    if (profile?.profilePictureUrl) {
      // API is hosted on port 8000 (backend). But api client uses /api.
      // Static files are mounted at /uploads.
      const baseUrl = import.meta.env.VITE_API_URL?.replace('/api', '') || 'http://localhost:8000';
      return `${baseUrl}${profile.profilePictureUrl}`;
    }
    return null;
  };

  return (
    <div className="min-h-[calc(100vh-80px)] p-6 bg-[#0B0F19] text-white">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header / Banner */}
        <div className="relative rounded-2xl overflow-hidden bg-gradient-to-r from-brandBlue/20 to-purple-900/20 border border-white/10 backdrop-blur-sm p-8">
          <div className="absolute top-0 right-0 p-32 bg-brandBlue/30 rounded-full blur-[100px] opacity-50 pointer-events-none" />
          
          <div className="relative z-10 flex flex-col md:flex-row items-center md:items-start gap-8">
            {/* Avatar Section */}
            <div className="relative group">
              <div className="w-32 h-32 rounded-full border-4 border-[#0B0F19] bg-brandBlue/20 flex items-center justify-center overflow-hidden shadow-2xl">
                {getProfilePicture() ? (
                  <img src={getProfilePicture()!} alt="Profile" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-4xl font-bold text-brandBlue">{profile?.initials}</span>
                )}
              </div>
              
              {/* Upload Button Overlay */}
              <button 
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="absolute inset-0 bg-black/60 rounded-full flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
              >
                {isUploading ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-white animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                ) : (
                  <>
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-white mb-1"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>
                    <span className="text-xs font-medium">Değiştir</span>
                  </>
                )}
              </button>
              
              <input 
                type="file" 
                ref={fileInputRef} 
                className="hidden" 
                accept="image/jpeg, image/png, image/webp" 
                onChange={handleFileChange}
              />
            </div>
            
            {/* Profile Info */}
            <div className="text-center md:text-left pt-2">
              <h1 className="text-3xl font-bold tracking-tight mb-2">{profile?.fullName}</h1>
              <p className="text-slate-400 font-medium mb-4">{profile?.tcNo}</p>
              
              <div className="flex flex-wrap items-center justify-center md:justify-start gap-4 text-sm mb-4">
                <Link to="/settings" className="flex items-center gap-2 px-4 py-2 bg-brandBlue text-white rounded-lg font-medium hover:bg-brandBlue/90 transition-colors shadow-lg shadow-brandBlue/20">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                  Ayarlara Git
                </Link>
              </div>

              <div className="flex flex-wrap items-center justify-center md:justify-start gap-4 text-sm">
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-slate-300">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-brandBlue"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>
                  <span>Katılım: {joinDate}</span>
                </div>
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>
                  <span>Doğrulanmış</span>
                </div>
              </div>
              
              {uploadError && (
                <p className="mt-4 text-red-400 text-sm font-medium">{uploadError}</p>
              )}
            </div>
          </div>
        </div>

        {/* Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* İletişim Bilgileri */}
          <div className="col-span-1 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 text-brandBlue"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.48 12H2"/></svg>
              İletişim Bilgileri
            </h2>
            
            <div className="space-y-6">
              <div className="group">
                <p className="text-xs text-slate-400 mb-1 font-medium uppercase tracking-wider">E-posta Adresi</p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-brandBlue/20 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 text-slate-300 group-hover:text-brandBlue transition-colors"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                  </div>
                  <span className="font-medium text-slate-200">{profile?.email}</span>
                </div>
              </div>
              
              <div className="group">
                <p className="text-xs text-slate-400 mb-1 font-medium uppercase tracking-wider">Telefon Numarası</p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-brandBlue/20 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 text-slate-300 group-hover:text-brandBlue transition-colors"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                  </div>
                  <span className="font-medium text-slate-200">{profile?.phoneNumber || 'Belirtilmedi'}</span>
                </div>
              </div>
            </div>
          </div>
          
          {/* İstatistikler ve Limitler */}
          <div className="col-span-1 lg:col-span-2 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md p-6">
            <h2 className="text-lg font-semibold mb-6 flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 text-purple-400"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/></svg>
              Güvenlik ve Limitler
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-gradient-to-br from-white/5 to-transparent border border-white/5">
                <p className="text-sm text-slate-400 mb-2">Günlük Transfer Limiti</p>
                <div className="flex items-end gap-2">
                  <p className="text-2xl font-bold">{(profile?.transactionLimit || 50000).toLocaleString('tr-TR')}</p>
                  <p className="text-sm text-slate-400 mb-1">₺</p>
                </div>
                <div className="mt-4 w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-brandBlue w-1/3 rounded-full" />
                </div>
                <p className="text-xs text-slate-500 mt-2">Kullanılan: 12.450 ₺</p>
              </div>
              
              <div className="p-4 rounded-xl bg-gradient-to-br from-white/5 to-transparent border border-white/5">
                <p className="text-sm text-slate-400 mb-2">Bildirim Tercihleri</p>
                <div className="space-y-3 mt-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">Güvenlik (Giriş vb.)</span>
                    <span className="text-xs px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded">Aktif</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">Hesap Hareketleri</span>
                    <span className="text-xs px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded">Aktif</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">Piyasa Uyarıları</span>
                    <span className="text-xs px-2 py-1 bg-slate-500/20 text-slate-400 rounded">Pasif</span>
                  </div>
                </div>
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  );
}
